"""Run live chat completions against multiple LLM providers.

This script uses the unified :class:`LLMClientAdaptor` to issue real API calls
for each configured provider. It only attempts providers whose required API key
is present in the environment, printing a helpful message for any that are
missing. Responses are truncated for readability.

Usage example::

    RUN_LLM_INTEGRATION_TESTS=1 \
    OPENAI_API_KEY=... GOOGLE_API_KEY=... \
    python mcp_kb/llm_live_demo.py --providers openai google anthropic

Available command-line flags are documented in ``main`` below. Be mindful that
executing this script may incur costs depending on the providers/models you
invoke.
"""
from __future__ import annotations

import argparse
import os
import textwrap
import time
from typing import Dict, Optional

from llm_client_adaptor import LLMClientAdaptor

# Provider configuration: environment variable names and sensible defaults.
PROVIDER_CONFIGS: Dict[str, Dict[str, Optional[str]]] = {
    "openai": {
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("openai"),
    },
    "google": {
        "model_env": "GOOGLE_MODEL",
        "default_model": "gemini-2.5-flash",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("google"),
    },
    "anthropic": {
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-sonnet-4-20250514",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("anthropic"),
    },
    "xai": {
        "model_env": "XAI_MODEL",
    "default_model": "grok-4",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("xai"),
        "base_url_env": "XAI_BASE_URL",
    },
    "mistral": {
        "model_env": "MISTRAL_MODEL",
        "default_model": "mistral-large-2411",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("mistral"),
    },
    "zai": {
        "model_env": "ZAI_MODEL",
        "default_model": "glm-4.5",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("zai"),
    },
    "deepseek": {
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("deepseek"),
    },
    "ollama": {
        "model_env": "OLLAMA_MODEL",
        "default_model": "gpt-oss",
        "api_key_env": LLMClientAdaptor.ENV_API_KEYS.get("ollama"),
        "base_url_env": "OLLAMA_BASE_URL",
        "default_base_url": "https://chatmol.org/ollama/api",
    },
}

CHEM_PROMPTS: Dict[str, str] = {
    "openai": "Share a quirky chemistry fact in one sentence.",
    "google": "What is a catalyst? Reply in one concise sentence.",
    "anthropic": "Describe the periodic table in ≤ 15 words.",
    "xai": "Name one famous chemist and why they are known.",
    "mistral": "Give a short definition of stoichiometry.",
    "zai": "Explain what molarity measures.",
    "deepseek": "Summarise an acid-base reaction in one sentence.",
    "ollama": "List one laboratory safety precaution.",
}


def _get_env_or_default(name: Optional[str], default: Optional[str]) -> Optional[str]:
    return os.getenv(name, default) if name else default


def _build_messages(prompt: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "You are a concise educational assistant responding for a chemistry tutor demo.",
        },
        {"role": "user", "content": prompt},
    ]


def call_provider(
    provider: str,
    *,
    prompt: Optional[str] = None,
    temperature: float = 0.5,
    max_tokens: int = 200,
    timeout: int = 120,
) -> None:
    config = PROVIDER_CONFIGS[provider]
    api_key_env = config.get("api_key_env")
    if api_key_env and provider != "ollama" and not os.getenv(api_key_env):
        print(f"[skip] {provider}: missing required environment variable {api_key_env}")
        return

    model = _get_env_or_default(config.get("model_env"), config.get("default_model"))
    base_url = _get_env_or_default(config.get("base_url_env"), config.get("default_base_url"))

    print(f"\n=== {provider.upper()} ===")
    print(f"model: {model}")
    if base_url:
        print(f"base_url: {base_url}")

    adaptor = LLMClientAdaptor(provider=provider, model=model, base_url=base_url, timeout=timeout)

    messages = _build_messages(prompt or CHEM_PROMPTS.get(provider, "Provide a short helpful response."))
    start = time.time()
    try:
        response = adaptor.chat(messages, temperature=temperature, max_tokens=max_tokens)
    except Exception as exc:  # pragma: no cover - live network exceptions
        print(f"[error] {provider}: {exc}")
        return
    duration = time.time() - start

    trimmed = response.strip()
    if len(trimmed) > 500:
        trimmed = trimmed[:497] + "..."

    print(textwrap.indent(trimmed or "<empty response>", prefix="  "))
    print(f"  (elapsed: {duration:.2f}s)\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live chat requests against multiple LLM providers.")
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["openai", "google", "anthropic", "xai", "mistral", "zai", "deepseek", "ollama"],
        choices=sorted(PROVIDER_CONFIGS.keys()),
        help="Subset of providers to query (default: all).",
    )
    parser.add_argument("--prompt", help="Override the prompt used for every provider.")
    parser.add_argument("--max-tokens", type=int, default=200, help="Maximum tokens per completion (default: 200).")
    parser.add_argument("--temperature", type=float, default=0.5, help="Sampling temperature (default: 0.5).")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-request timeout in seconds (default: 120).",
    )
    args = parser.parse_args()

    print("Starting live LLM demo...\n")
    for provider in args.providers:
        call_provider(
            provider,
            prompt=args.prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )


if __name__ == "__main__":
    main()
