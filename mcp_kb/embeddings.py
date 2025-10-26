"""
Embedding utilities: EmbeddingGenerator and semantic similarity.
Split out from utils.py for modularity.
"""
from typing import List, Optional, Any
import numpy as np
from openai import OpenAI

# Absolute imports within workspace
from content_processing import ContentChunk  # for type hints only


class EmbeddingGenerator:
    """Handles embedding generation for different types of content."""

    def __init__(self, model: str = "text-embedding-3-large", batch_size: int = 32):
        self.model = model
        self.batch_size = batch_size
        self.client = OpenAI()

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.
        """
        if not texts:
            return np.array([])

        cleaned_texts = [text.replace("\n", " ").strip() for text in texts if text.strip()]
        if not cleaned_texts:
            return np.array([])

        embeddings: List[List[float]] = []
        n_batches = (len(cleaned_texts) + self.batch_size - 1) // self.batch_size
        print(f"Generating embeddings for {len(cleaned_texts)} texts in {n_batches} batches...")

        for i in range(n_batches):
            start_idx = i * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(cleaned_texts))
            batch_texts = cleaned_texts[start_idx:end_idx]
            try:
                response = self.client.embeddings.create(input=batch_texts, model=self.model)
                batch_embeddings = [d.embedding for d in response.data]
                embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"Error generating embeddings for batch {i+1}: {e}")
                embedding_dim = 3072 if "large" in self.model else 1536
                zero_embeddings = [[0.0] * embedding_dim] * len(batch_texts)
                embeddings.extend(zero_embeddings)

        return np.array(embeddings)

    def generate_header_embedding(self, header: str) -> Optional[np.ndarray]:
        if not header or header.strip() in ["", "Root"]:
            return None
        embeddings = self.generate_embeddings([header])
        return embeddings[0] if len(embeddings) > 0 else None

    def generate_summary_embedding(self, summary: str) -> Optional[np.ndarray]:
        if not summary or not summary.strip():
            return None
        embeddings = self.generate_embeddings([summary])
        return embeddings[0] if len(embeddings) > 0 else None

    def generate_chunk_embeddings(self, chunks: List[ContentChunk]) -> np.ndarray:
        if not chunks:
            return np.array([])
        chunk_texts = [chunk.content for chunk in chunks if str(getattr(chunk, 'content', '')).strip()]
        return self.generate_embeddings(chunk_texts)

    def generate_sentence_embeddings(self, sentences: List[str]) -> np.ndarray:
        if not sentences:
            return np.array([])
        valid_sentences = [sent for sent in sentences if sent.strip()]
        return self.generate_embeddings(valid_sentences)


def calculate_semantic_similarity(query_embedding: np.ndarray,
                                  content_embeddings: Optional[np.ndarray],
                                  header_embedding: Optional[np.ndarray],
                                  summary_embedding: Optional[np.ndarray],
                                  chunk_embeddings: Optional[np.ndarray] = None,
                                  sentence_embeddings: Optional[np.ndarray] = None,
                                  question_embeddings: Optional[np.ndarray] = None,
                                  weights: Optional[Any] = None) -> float:
    """Calculate weighted semantic similarity across available embedding types."""
    if weights is None:
        try:
            from parameters import DEFAULT_PARAMETERS
            weights = DEFAULT_PARAMETERS.semantic_weights
        except Exception:
            from dataclasses import dataclass
            @dataclass
            class FallbackWeights:
                header: float = 0.15
                summary: float = 0.15
                content: float = 0.15
                chunks: float = 0.15
                sentences: float = 0.15
                questions: float = 0.25
            weights = FallbackWeights()

    total_score = 0.0
    total_weight = 0.0

    if header_embedding is not None:
        total_score += weights.header * float(np.dot(query_embedding, header_embedding))
        total_weight += weights.header

    if summary_embedding is not None:
        total_score += weights.summary * float(np.dot(query_embedding, summary_embedding))
        total_weight += weights.summary

    if content_embeddings is not None:
        if content_embeddings.ndim == 1:
            content_sim = float(np.dot(query_embedding, content_embeddings))
        else:
            content_sim = float(np.max(np.dot(query_embedding, content_embeddings.T)))
        total_score += weights.content * content_sim
        total_weight += weights.content

    if chunk_embeddings is not None and len(chunk_embeddings) > 0:
        if chunk_embeddings.ndim == 1:
            chunk_sim = float(np.dot(query_embedding, chunk_embeddings))
        else:
            chunk_sim = float(np.max(np.dot(query_embedding, chunk_embeddings.T)))
        total_score += weights.chunks * chunk_sim
        total_weight += weights.chunks

    if sentence_embeddings is not None and len(sentence_embeddings) > 0:
        if sentence_embeddings.ndim == 1:
            sentence_sim = float(np.dot(query_embedding, sentence_embeddings))
        else:
            sentence_sim = float(np.max(np.dot(query_embedding, sentence_embeddings.T)))
        total_score += weights.sentences * sentence_sim
        total_weight += weights.sentences

    if question_embeddings is not None and len(question_embeddings) > 0:
        if question_embeddings.ndim == 1:
            question_sim = float(np.dot(query_embedding, question_embeddings))
        else:
            question_sim = float(np.max(np.dot(query_embedding, question_embeddings.T)))
        total_score += weights.questions * question_sim
        total_weight += weights.questions

    return total_score / total_weight if total_weight > 0 else 0.0
