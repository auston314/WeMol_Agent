"""
Compatibility layer for refactored utilities.

This module re-exports key classes and functions from the new, smaller modules:
- nlp_utils: STOP_WORDS, extract_sentences_from_text
- content_processing: ContentChunk, ContentProcessor
- embeddings: EmbeddingGenerator, calculate_semantic_similarity
- indexing: InverseIndexBuilder
- content_enhancer: ContentEnhancer

Existing code importing from `utils` will continue to work.
"""

from nlp_utils import STOP_WORDS, extract_sentences_from_text
from content_processing import ContentChunk, ContentProcessor
from embeddings import EmbeddingGenerator, calculate_semantic_similarity
from indexing import InverseIndexBuilder
from content_enhancer import ContentEnhancer

__all__ = [
    # NLP
    "STOP_WORDS",
    "extract_sentences_from_text",
    # Processing
    "ContentChunk",
    "ContentProcessor",
    # Embeddings
    "EmbeddingGenerator",
    "calculate_semantic_similarity",
    # Indexing
    "InverseIndexBuilder",
    # Orchestrator
    "ContentEnhancer",
]
