"""
Lightweight NLP utilities shared across modules.
Initializes NLTK resources, exposes STOP_WORDS and sentence extraction.
"""

from typing import List
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize

# Ensure required NLTK data is available
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')

# Export English stopwords
STOP_WORDS = set(stopwords.words('english'))


def extract_sentences_from_text(text: str) -> List[str]:
    """Extract sentences from text using NLTK with a simple fallback.

    Returns a list of cleaned sentences, skipping very short fragments.
    """
    if not text or not text.strip():
        return []
    try:
        sentences = sent_tokenize(text)
        cleaned = []
        for s in sentences:
            s = s.strip()
            if s and len(s) > 10:
                cleaned.append(s)
        return cleaned
    except Exception:
        # Fallback to regex-based splitter
        parts = re.split(r'[.!?]+\s+', text)
        return [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
