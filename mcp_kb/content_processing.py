"""
Content processing utilities: ContentChunk and ContentProcessor.
Split out from utils.py for better modularity.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import re
import json
import requests
from openai import OpenAI

from nlp_utils import extract_sentences_from_text


@dataclass
class ContentChunk:
    """Represents a chunk of content with its type and processed information."""
    content: str
    chunk_type: str  # 'paragraph', 'table', 'figure', 'code', 'pre-formatted'
    sentences: List[str]
    word_count: int

    def __post_init__(self):
        if not self.sentences:
            self.sentences = extract_sentences_from_text(self.content)
        if not self.word_count:
            self.word_count = len(self.content.split())


class ContentProcessor:
    """Handles content processing tasks for ContentNode objects."""

    def __init__(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b',
                 llm_api_url: str = 'https://chatmol.org/ollama/api/generate'):
        self.llm_type = llm_type.lower()
        self.llm_model = llm_model
        self.llm_api_url = llm_api_url

        if self.llm_type == 'openai':
            self.openai_client = OpenAI()
        elif self.llm_type == 'zai':
            try:
                from zai import ZaiClient
                import os
                self.zai_client = ZaiClient(api_key=os.environ.get('ZAI_API_KEY'))
            except ImportError:
                raise ImportError("ZAI client not found. Please install the zai package.")
            except KeyError:
                raise ValueError("ZAI_API_KEY environment variable not set.")
        elif self.llm_type != 'ollama':
            raise ValueError(f"Unsupported LLM type: {llm_type}. Supported types: 'ollama', 'openai', 'zai'")

    # Unified LLM caller wrappers (moved from utils)
    def _call_openai_api(self, prompt: str, system_message: str = "", temperature: float = 0.1, max_tokens: int = 1024) -> str:
        try:
            import re as _re
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
            is_gpt5 = bool(_re.match(r"^\s*gpt-5", str(self.llm_model), _re.IGNORECASE))
            kwargs = {
                "model": self.llm_model,
                "messages": messages,
                "temperature": 1 if is_gpt5 else temperature,
            }
            if is_gpt5:
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens

            response = self.openai_client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = (getattr(choice, "message", None).content or "").strip() if getattr(choice, "message", None) else ""

            if (not content) and getattr(choice, "finish_reason", None) == "length":
                retry_kwargs = dict(kwargs)
                retry_messages = list(messages)
                retry_messages[0] = {
                    "role": "system",
                    "content": (system_message + " Be extremely concise. Return no more than 120 words.").strip()
                }
                retry_kwargs["messages"] = retry_messages
                if is_gpt5:
                    retry_kwargs["max_completion_tokens"] = min(8192, max_tokens * 2)
                else:
                    retry_kwargs["max_tokens"] = min(8192, max_tokens * 2)
                response2 = self.openai_client.chat.completions.create(**retry_kwargs)
                choice2 = response2.choices[0]
                content2 = (getattr(choice2, "message", None).content or "").strip() if getattr(choice2, "message", None) else ""
                return content2

            return content
        except Exception as e:
            err_msg = str(e)
            try:
                if "temperature" in err_msg and ("unsupported" in err_msg.lower() or "Only the default (1) value is supported" in err_msg):
                    messages = [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ]
                    import re as _re
                    is_gpt5 = bool(_re.match(r"^\s*gpt-5", str(self.llm_model), _re.IGNORECASE))
                    kwargs = {"model": self.llm_model, "messages": messages}
                    if is_gpt5:
                        kwargs["max_completion_tokens"] = max_tokens
                    else:
                        kwargs["max_tokens"] = max_tokens
                    response = self.openai_client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content.strip()
                if "max_tokens" in err_msg and "max_completion_tokens" in err_msg:
                    messages = [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ]
                    kwargs = {"model": self.llm_model, "messages": messages, "max_completion_tokens": max_tokens}
                    response = self.openai_client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content.strip()
                if "unexpected keyword argument" in err_msg and "reasoning" in err_msg:
                    messages = [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ]
                    import re as _re
                    is_gpt5 = bool(_re.match(r"^\s*gpt-5", str(self.llm_model), _re.IGNORECASE))
                    kwargs = {"model": self.llm_model, "messages": messages, "temperature": 1 if is_gpt5 else temperature}
                    if is_gpt5:
                        kwargs["max_completion_tokens"] = max_tokens
                    else:
                        kwargs["max_tokens"] = max_tokens
                    response = self.openai_client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content.strip()
            except Exception as e2:
                print(f"Error calling OpenAI API (retry): {e2}")
            print(f"Error calling OpenAI API: {e}")
            return ""

    def _call_zai_api(self, prompt: str, system_message: str = "", temperature: float = 0.1, max_tokens: int = 1024) -> str:
        try:
            response = self.zai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                top_p=0.8
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error calling Z.AI API: {e}")
            return ""

    def _call_ollama_api(self, prompt: str, system_message: str = "", temperature: float = 0.1, max_tokens: int = 1024) -> str:
        try:
            full_prompt = f"System: {system_message}\n\nUser: {prompt}" if system_message else prompt
            payload = {
                'model': self.llm_model,
                'prompt': full_prompt,
                'options': {'temperature': temperature},
                'stream': False,
            }
            response = requests.post(self.llm_api_url, json=payload, stream=False)
            data = response.json()
            if 'error' in data:
                raise Exception(f"Ollama API error: {data['error']}")
            return data.get('response', '')
        except Exception as e:
            print(f"Error calling Ollama API: {e}")
            return ""

    def _call_llm_unified(self, prompt: str, system_message: str = "", temperature: float = 0.1, max_tokens: int = 4096) -> str:
        if self.llm_type == 'openai':
            return self._call_openai_api(prompt, system_message, temperature, max_tokens)
        elif self.llm_type == 'zai':
            return self._call_zai_api(prompt, system_message, temperature, max_tokens)
        elif self.llm_type == 'ollama':
            return self._call_ollama_api(prompt, system_message, temperature, max_tokens)
        else:
            raise ValueError(f"Unsupported LLM type: {self.llm_type}")

    def generate_content_summary(self, content_text: str, max_words: int = 30) -> str:
        content_text = content_text.strip()
        if not content_text:
            return ""
        print("Generating summary...")
        system_message = (
            f"You are an expert at summarizing text. Please create a concise summary of the given text with no more than {max_words} words. "
            f"Keep summary clean, no title or header is needed."
        )
        summary = self._call_llm_unified(content_text, system_message)
        return (summary or "").strip()

    def generate_keyword_list(self, content_text: str, max_keywords: int = 10) -> List[str]:
        content_text = content_text.strip()
        if not content_text:
            return []
        print("Generating keywords...")
        system_message = (
            f"Generate a list of keywords from the given text in no more than {max_keywords} words. "
            f"The keyword list should be in JSON list format. Only list the most important keywords. "
            f"Make your response clean, no title or header is needed. Return only the JSON array."
        )
        keywords_response = self._call_llm_unified(content_text, system_message)
        try:
            keywords = json.loads(keywords_response)
            return keywords if isinstance(keywords, list) else []
        except Exception:
            words = re.findall(r'\b[a-zA-Z]+\b', keywords_response or "")
            return words[:max_keywords]

    def create_content_chunks(self, content_text: str) -> List[ContentChunk]:
        if not content_text.strip():
            return []
        chunks: List[ContentChunk] = []
        figure_blocks = self._find_figure_blocks(content_text)
        patterns: Dict[str, str] = {
            'code': r'```[\s\S]*?```',
            'pre-formatted': r'<pre>[\s\S]*?</pre>',
            'table': r'(?:\|.*?\|\n)+',
        }
        special_blocks = []
        for figure_block in figure_blocks:
            special_blocks.append(figure_block)
        for block_type, pattern in patterns.items():
            for match in re.finditer(pattern, content_text):
                overlaps = False
                for fig_block in figure_blocks:
                    if (match.start() < fig_block['end'] and match.end() > fig_block['start']):
                        overlaps = True
                        break
                if not overlaps:
                    special_blocks.append({
                        'start': match.start(),
                        'end': match.end(),
                        'type': block_type,
                        'content': match.group()
                    })
        special_blocks.sort(key=lambda x: x['start'])
        last_end = 0
        for block in special_blocks:
            if block['start'] > last_end:
                paragraph_text = content_text[last_end:block['start']].strip()
                if paragraph_text:
                    paragraphs = re.split(r'\n\s*\n', paragraph_text)
                    for para in paragraphs:
                        para = para.strip()
                        if para:
                            chunks.append(ContentChunk(content=para, chunk_type='paragraph', sentences=[], word_count=0))
            chunks.append(ContentChunk(content=block['content'], chunk_type=block['type'], sentences=[], word_count=0))
            last_end = block['end']
        if last_end < len(content_text):
            remaining_text = content_text[last_end:].strip()
            if remaining_text:
                paragraphs = re.split(r'\n\s*\n', remaining_text)
                for para in paragraphs:
                    para = para.strip()
                    if para:
                        chunks.append(ContentChunk(content=para, chunk_type='paragraph', sentences=[], word_count=0))
        return chunks

    def _find_figure_blocks(self, content_text: str) -> List[Dict]:
        figure_blocks: List[Dict] = []
        image_pattern = r'!\[.*?\]\([^)]+\)'
        for match in re.finditer(image_pattern, content_text):
            image_start = match.start()
            image_end = match.end()
            image_content = match.group()
            remaining_text = content_text[image_end:]
            caption_match = re.match(r'\s*\n?\s*(Figure\s+[\d.]+[^\n]*(?:\n(?!\s*\n)[^\n]*)*)', remaining_text, re.IGNORECASE)
            if caption_match:
                caption_content = caption_match.group(1).strip()
                caption_end = image_end + caption_match.end()
                full_figure_content = content_text[image_start:caption_end]
                figure_blocks.append({'start': image_start, 'end': caption_end, 'type': 'figure', 'content': full_figure_content})
            else:
                caption_match = re.match(r'\s*\n?\s*([^\n]+(?:\n(?!\s*\n)[^\n]*)*)', remaining_text)
                if caption_match:
                    potential_caption = caption_match.group(1).strip()
                    if (len(potential_caption) > 20 and not potential_caption.startswith(('!', '#', '```', '|')) and not re.match(r'^\s*$', potential_caption)):
                        caption_end = image_end + caption_match.end()
                        full_figure_content = content_text[image_start:caption_end]
                        figure_blocks.append({'start': image_start, 'end': caption_end, 'type': 'figure', 'content': full_figure_content})
                    else:
                        figure_blocks.append({'start': image_start, 'end': image_end, 'type': 'figure', 'content': image_content})
                else:
                    figure_blocks.append({'start': image_start, 'end': image_end, 'type': 'figure', 'content': image_content})
        return figure_blocks

    def extract_sentences_from_content(self, content_text: str) -> List[str]:
        if not content_text.strip():
            return []
        return extract_sentences_from_text(content_text)

    def generate_questions_json(self, content_text: str, max_questions: int = 50) -> List[str]:
        content_text = content_text.strip()
        if not content_text:
            return []
        print("Generating study questions...")
        system_message = (
            "You are an expert question generator for textbooks.\n"
            "Analyze the text carefully. Internally identify all key facts, relationships, and entities.\n"
            "Then generate diverse, specific questions that can be answered using ONLY the provided text.\n"
            "Return STRICTLY a JSON array of strings (questions) and nothing else.\n"
            "Requirements:\n"
            f"- Up to {max_questions} questions.\n"
            "- Cover main facts, relationships, and entities.\n"
            "- Each question must be clear, self-contained, and answerable from the text alone.\n"
            "- Prefer who/what/when/where/why/how, definitions, comparisons, mechanisms, causes, consequences.\n"
            "- Avoid yes/no when possible and avoid referencing 'the text' or 'according to the text'.\n"
            "- Do not include questions that are too similar to each other.\n"
            "- Put more emphasis on important concepts.\n"
            "- Do not include answers."
        )
        response = self._call_llm_unified(content_text, system_message)
        s = (response or "").strip()
        if not s:
            return []
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(q).strip() for q in data if str(q).strip()]
        except Exception:
            pass
        m = re.search(r"\[[\s\S]*\]", s)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, list):
                    return [str(q).strip() for q in data if str(q).strip()]
            except Exception:
                pass
        lines = [ln.strip().lstrip("-*0123456789. ").strip() for ln in s.splitlines()]
        questions = [ln for ln in lines if ln]
        return questions
