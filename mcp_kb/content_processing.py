"""
Content processing utilities: ContentChunk and ContentProcessor.
Split out from utils.py for better modularity.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import re
import json

from llm_client_adaptor import LLMClientAdaptor

from nlp_utils import extract_sentences_from_text

DEFAULT_LLM_PROVIDER = "ollama"
DEFAULT_LLM_MODEL = "qwen2.5vl:32b"
DEFAULT_LLM_BASE_URL = "https://chatmol.org/ollama/api/generate"


def ensure_llm_client_adaptor(llm_client_adaptor: Optional[LLMClientAdaptor] = None) -> LLMClientAdaptor:
    """Return a usable ``LLMClientAdaptor`` instance, constructing a default when needed."""
    if llm_client_adaptor is not None:
        return llm_client_adaptor
    return LLMClientAdaptor(
        provider=DEFAULT_LLM_PROVIDER,
        model=DEFAULT_LLM_MODEL,
        base_url=DEFAULT_LLM_BASE_URL,
    )


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

    def __init__(self, llm_client_adaptor: Optional[LLMClientAdaptor] = None):
        try:
            self.llm_adaptor = ensure_llm_client_adaptor(llm_client_adaptor)
        except ValueError as exc:
            raise ValueError(str(exc))
        self.provider_name = getattr(self.llm_adaptor, "provider", "unknown")

    # Unified LLM caller wrapper (moved from utils)
    def _call_llm_unified(self, prompt: str, system_message: str = "", temperature: float = 0.1, max_tokens: int = 4096) -> str:
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        try:
            return self.llm_adaptor.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            print(f"Error calling {self.provider_name} API: {exc}")
            return ""

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
    
    def generate_knowledge_list(self, content_text:str) -> str:
        content_text= content_text.strip()
        print("Generating knowledge list...")
        #system_message= "You are extremely skilled in generating knowledge graphs. Please create a knowledge graph of key facts, concepts of chemistry, properties and relationships."
        system_message= "You are extremely skilled expert to extract knowledge from a documentg. Please create a list of key facts, concepts of chemistry, properties and relationships that are included in the provided content."
        knowledge_list = self._call_llm_unified(content_text, system_message)
        return knowledge_list
       
    def generate_questions(self, content_text:str, summary:str, knowledge_graph:str, max_questions:int) -> str:
        #knowledge_graph= self.generate_knowledge_graph(content_text)
        #summary= self.generate_content_summary(content_text)
        system_message = f"""You will generate a list of questions based on the given text, its summary and knowledge list according to the following rules:
        
        1. Please put one question per line, and DO NOT include any additional text. No answers are needed, just the questions.
        2. Make sure you generate the more generic questions about the most important concepts first, and then generate more granular, specific questions.
        3. Make sure to avoid similar questions.
        4. Make sure the questions are answerable based on the provided content. 
        5. Each question should be clear and self-contained, without needing additional context.
        6. Make sure no more than {max_questions} questions will be created.
        """
        print("Generating questions based on content, summary and knowledge list...")
        combined_prompt = f"Summary: {summary}\n\nKnowledge Graph: {knowledge_graph}\n\nOriginal Text: {content_text}"
        questions = self._call_llm_unified(combined_prompt, system_message)
        question_list = questions.split("\n")
        question_list = [question.strip() for question in question_list if len(question) > 1] # Remove blank lines
        return question_list