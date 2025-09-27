"""Unified LLM client adaptor supporting multiple providers.

This module exposes :class:`LLMClientAdaptor`, a thin abstraction that normalises
chat-style interactions across a range of third-party LLM APIs.  Each provider
is wrapped behind a single ``chat`` method that accepts an OpenAI-compatible
list of messages and returns the assistant's textual response.

Supported providers: OpenAI, Google (Gemini), Anthropic, xAI, Mistral,
Zhipu/GLM (``zai``), DeepSeek, and Ollama.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover - import guard for optional dependency
    import requests  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'requests' package is required to use LLMClientAdaptor. Please install it via pip."
    ) from exc

__all__ = ["LLMClientAdaptor"]

logger = logging.getLogger(__name__)


class LLMClientAdaptor:
    """Provide a unified chat interface across multiple LLM providers.

    Parameters
    ----------
    provider:
        Name of the LLM provider (case-insensitive). Aliases such as
        ``antropic`` -> ``anthropic`` or ``glm`` -> ``zai`` are supported.
    model:
        Model identifier to request from the provider.
    base_url:
        Optional override for the provider's API base URL. If omitted, a
        sensible default is used per provider.
    api_key:
        Optional explicit API key. When absent, the adaptor looks up the key
        from the standard environment variables documented in the README.
    timeout:
        HTTP timeout (seconds) applied to outbound requests.
    session:
        Optional ``requests.Session`` instance. One is created automatically if
        not supplied.
    """

    PROVIDER_ALIASES: Dict[str, str] = {
        "openai": "openai",
        "google": "google",
        "gemini": "google",
        "anthropic": "anthropic",
        "antropic": "anthropic",
        "claude": "anthropic",
        "xai": "xai",
        "grok": "xai",
        "mistral": "mistral",
        "zai": "zai",
        "glm": "zai",
        "zhipu": "zai",
        "deepseek": "deepseek",
        "ollama": "ollama",
    }

    DEFAULT_BASE_URLS: Dict[str, str] = {
        "openai": "https://api.openai.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
        "anthropic": "https://api.anthropic.com/v1",
    "xai": "https://api.x.ai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "zai": "https://open.bigmodel.cn/api/paas/v4",
        "deepseek": "https://api.deepseek.com/v1",
    "ollama": "https://chatmol.org/ollama/api",
    }

    ENV_API_KEYS: Dict[str, str] = {
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "xai": "XAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "zai": "ZAI_API_KEY",
        "deepseek": "DS_API_KEY",
        "ollama": "OLLAMA_API_KEY",  # typically not required
    }

    _GOOGLE_ROLE_MAP: Dict[str, str] = {
        "system": "user",  # system instructions handled separately
        "assistant": "model",
        "user": "user",
    }

    def __init__(
        self,
        provider: str,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 60,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not provider:
            raise ValueError("Provider name must be supplied")
        if not model:
            raise ValueError("Model name must be supplied")

        self.provider = self._normalise_provider(provider)
        self.model = model
        self.timeout = timeout
        self.session = session or requests.Session()

        default_base = self.DEFAULT_BASE_URLS.get(self.provider)
        if not default_base and not base_url:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        self.base_url = (base_url or default_base).rstrip("/")

        env_key_name = self.ENV_API_KEYS.get(self.provider)
        self.api_key = api_key or (env_key_name and os.getenv(env_key_name))
        if self.provider != "ollama" and not self.api_key:
            raise ValueError(
                f"Missing API key for provider '{self.provider}'. Set {env_key_name} or pass api_key explicitly."
            )

        self._handlers = {
            "openai": self._chat_openai,
            "google": self._chat_google,
            "anthropic": self._chat_anthropic,
            "xai": self._chat_xai,
            "mistral": self._chat_mistral,
            "zai": self._chat_zai,
            "deepseek": self._chat_deepseek,
            "ollama": self._chat_ollama,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: Iterable[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request and return the assistant response."""
        prepared_messages = self._prepare_messages(messages)
        handler = self._handlers.get(self.provider)
        if handler is None:
            raise ValueError(f"Unsupported provider '{self.provider}'")

        try:
            response_text = handler(
                prepared_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except requests.HTTPError as http_err:
            logger.error("HTTP error from %s: %s", self.provider, http_err, exc_info=True)
            raise
        except Exception:
            logger.exception("Unexpected error while calling provider '%s'", self.provider)
            raise

        if isinstance(response_text, str):
            return response_text.strip()
        if response_text is None:
            return ""
        # Fallback: convert structured responses to JSON string
        return json.dumps(response_text)

    # ------------------------------------------------------------------
    # Provider-specific handlers
    # ------------------------------------------------------------------
    def _chat_openai(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        payload: Dict[str, Any] = {"model": self.model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = 1.0 if self._is_gpt5_model() else temperature
        if max_tokens is not None:
            token_field = "max_completion_tokens" if self._is_gpt5_model() else "max_tokens"
            payload[token_field] = max_tokens
        if self._is_gpt5_model():
            # Ensure GPT-5 Codex previews are opted-in with sensible defaults.
            payload.setdefault("temperature", 1.0)
            payload.setdefault("reasoning", {"effort": kwargs.pop("reasoning_effort", "medium")})
        payload.update(kwargs)

        headers = self._json_headers(bearer=True)
        data = self._post("chat/completions", headers=headers, payload=payload)
        return self._extract_choice_content(data)

    def _chat_google(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        system_instruction, conversation = self._split_system_messages(messages)
        contents = [
            {
                "role": self._GOOGLE_ROLE_MAP.get(msg["role"], "user"),
                "parts": [{"text": self._ensure_text(msg.get("content", ""))}],
            }
            for msg in conversation
        ]
        payload: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = {
                "role": "system",
                "parts": [{"text": system_instruction}],
            }
        generation_config: Dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if generation_config:
            payload["generationConfig"] = generation_config
        if kwargs:
            payload.update(kwargs)

        endpoint = f"models/{self.model}:generateContent"
        headers = self._json_headers(bearer=False)
        params = {"key": self.api_key}
        data = self._post(endpoint, headers=headers, payload=payload, params=params)
        candidates = data.get("candidates") or []
        if candidates:
            first = candidates[0]
            content = first.get("content") or {}
            parts = content.get("parts") or []
            if parts:
                return self._ensure_text(parts[0].get("text", ""))
        return ""

    def _chat_anthropic(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        system_instruction, conversation = self._split_system_messages(messages)
        anthropic_messages = [
            {
                "role": msg["role"] if msg["role"] in {"user", "assistant"} else "user",
                "content": [{"type": "text", "text": self._ensure_text(msg.get("content", ""))}],
            }
            for msg in conversation
        ]
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or kwargs.pop("max_tokens", 1024),
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if system_instruction:
            payload["system"] = system_instruction
        if kwargs:
            payload.update(kwargs)

        if not self.api_key:
            raise ValueError("Anthropic API key missing; ensure ANTHROPIC_API_KEY is set.")
        headers = self._json_headers(
            bearer=False,
            extra={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        data = self._post("messages", headers=headers, payload=payload)
        content = data.get("content") or []
        if content:
            first = content[0]
            if isinstance(first, dict):
                return self._ensure_text(first.get("text", ""))
        return ""

    def _chat_xai(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        return self._chat_openai_style(
            endpoint="chat/completions",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _chat_mistral(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        return self._chat_openai_style(
            endpoint="chat/completions",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _chat_zai(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        extra_payload = {"temperature": temperature} if temperature is not None else {}
        if max_tokens is not None:
            extra_payload["max_tokens"] = max_tokens
        extra_payload.update(kwargs)
        return self._chat_openai_style(
            endpoint="chat/completions",
            messages=messages,
            temperature=None,  # already passed via extra_payload
            max_tokens=None,
            extra_payload=extra_payload,
        )

    def _chat_deepseek(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        return self._chat_openai_style(
            endpoint="chat/completions",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _chat_ollama(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        headers = self._json_headers(bearer=False)
        stream = kwargs.pop("stream", False)
        options: Dict[str, Any] = kwargs.pop("options", {})
        if temperature is not None:
            options.setdefault("temperature", temperature)
        if max_tokens is not None:
            options.setdefault("num_predict", max_tokens)
        base_url = self.base_url.rstrip("/")
        prompt_text = self._messages_to_prompt(messages)

        if re.search(r"/(generate|chat)$", base_url):
            candidate_urls = [base_url]
        else:
            candidate_urls = [f"{base_url}/chat", f"{base_url}/generate", base_url]

        # Preserve order while removing duplicates.
        seen: set[str] = set()
        ordered_candidates: List[str] = []
        for url in candidate_urls:
            if url not in seen:
                seen.add(url)
                ordered_candidates.append(url)

        last_error: Optional[Exception] = None

        for target_url in ordered_candidates:
            if target_url.endswith("generate"):
                payload = {
                    "model": self.model,
                    "prompt": prompt_text,
                    "stream": stream,
                }
                if options:
                    payload["options"] = options
            else:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": stream,
                }
                if options:
                    payload["options"] = options

            try:
                response = self.session.post(target_url, headers=headers, json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as exc:
                last_error = exc
                continue

            if isinstance(data, dict):
                if "message" in data and isinstance(data["message"], dict):
                    return self._ensure_text(data["message"].get("content", ""))
                if "response" in data:
                    return self._ensure_text(data.get("response", ""))
                if "messages" in data and isinstance(data["messages"], list):
                    first = data["messages"][0] if data["messages"] else {}
                    if isinstance(first, dict):
                        return self._ensure_text(first.get("content", ""))
            return self._ensure_text(data)

        if last_error:
            raise last_error
        return ""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _chat_openai_style(
        self,
        endpoint: str,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        extra_payload: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> str:
        payload: Dict[str, Any] = {"model": self.model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if kwargs:
            payload.update(kwargs)
        if extra_payload:
            payload.update(extra_payload)

        headers = self._json_headers(bearer=True, extra=extra_headers)
        data = self._post(endpoint, headers=headers, payload=payload)
        return self._extract_choice_content(data)

    def _post(
        self,
        endpoint: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.post(url, headers=headers, json=payload, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _prepare_messages(self, messages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        prepared: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                raise ValueError("Each message must be a dict with 'role' and 'content'.")
            role = (msg.get("role") or "user").lower()
            content = msg.get("content", "")
            prepared.append({"role": role, "content": content})
        if not prepared:
            raise ValueError("At least one message must be supplied")
        return prepared

    @staticmethod
    def _ensure_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
        if isinstance(content, dict) and "text" in content:
            return str(content["text"])
        return str(content)

    def _split_system_messages(self, messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        system_parts: List[str] = []
        rest: List[Dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(self._ensure_text(msg.get("content", "")))
            else:
                rest.append(msg)
        return ("\n\n".join(part for part in system_parts if part.strip()), rest)

    def _messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "user").capitalize()
            content = self._ensure_text(msg.get("content", ""))
            lines.append(f"{role}: {content}")
        lines.append("Assistant:")
        return "\n\n".join(lines)

    def _json_headers(self, bearer: bool, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if bearer and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    def _extract_choice_content(self, data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if choices:
            first = choices[0]
            message = first.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
            if content is None and "delta" in first:
                delta = first.get("delta") or {}
                return delta.get("content", "")
        return ""

    def _is_gpt5_model(self) -> bool:
        return bool(re.match(r"^\s*gpt-5", self.model, re.IGNORECASE))

    @classmethod
    def _normalise_provider(cls, provider: str) -> str:
        key = provider.strip().lower()
        return cls.PROVIDER_ALIASES.get(key, key)
