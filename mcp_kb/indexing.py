"""
Inverse index builder and lexical similarity utilities.
Split out from utils.py for modularity.
"""
from typing import List, Dict, Optional, Any, Tuple
from collections import defaultdict
from dataclasses import dataclass
import re

from nlp_utils import STOP_WORDS


class InverseIndexBuilder:
    """Builds and manages inverse indexes for n-grams."""

    def __init__(self, include_stopwords: bool = False, parameters: Optional[Any] = None):
        self.include_stopwords = include_stopwords
        self.monogram_index: Dict[str, List[int]] = defaultdict(list)
        self.bigram_index: Dict[str, List[int]] = defaultdict(list)
        self.trigram_index: Dict[str, List[int]] = defaultdict(list)

        if parameters is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                self.parameters = DEFAULT_PARAMETERS
            except Exception:
                @dataclass
                class FallbackParameters:
                    class ngram_weights:
                        monogram: float = 1.0
                        bigram: float = 4.0
                        trigram: float = 9.0
                self.parameters = FallbackParameters()
        else:
            self.parameters = parameters

    def build_ngram_indexes(self, nodes: List[Any]) -> None:
        print("Building n-gram indexes...")
        for node in nodes:
            if (node.skip):
                print("  ⚠️ Node processing was skipped.")
                continue
            if hasattr(node, 'content_text') and node.content_text:
                self._add_node_to_indexes(node.node_id, node.content_text)
        print(f"Index stats: {len(self.monogram_index)} monograms, {len(self.bigram_index)} bigrams, {len(self.trigram_index)} trigrams")

    def _tokenize_and_clean(self, text: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z]+", text.lower())
        if not self.include_stopwords:
            tokens = [t for t in tokens if t not in STOP_WORDS]
        return tokens

    def _add_node_to_indexes(self, node_id: int, content_text: str) -> None:
        tokens = self._tokenize_and_clean(content_text)
        if not tokens:
            return
        monograms = tokens
        bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
        trigrams = [f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}" for i in range(len(tokens)-2)]
        for gram in monograms:
            if node_id not in self.monogram_index[gram]:
                self.monogram_index[gram].append(node_id)
        for gram in bigrams:
            if node_id not in self.bigram_index[gram]:
                self.bigram_index[gram].append(node_id)
        for gram in trigrams:
            if node_id not in self.trigram_index[gram]:
                self.trigram_index[gram].append(node_id)

    def _calculate_node_score(self, node_id: int, query_monograms: List[str], query_bigrams: List[str], query_trigrams: List[str], ngram_weights: Optional[Any]) -> float:
        if ngram_weights is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                ngram_weights = DEFAULT_PARAMETERS.ngram_weights
            except Exception:
                @dataclass
                class FallbackNGramWeights:
                    monogram: float = 1.0
                    bigram: float = 4.0
                    trigram: float = 9.0
                ngram_weights = FallbackNGramWeights()
        monogram_matches = sum(1 for gram in query_monograms if node_id in self.monogram_index.get(gram, []))
        bigram_matches = sum(1 for gram in query_bigrams if node_id in self.bigram_index.get(gram, []))
        trigram_matches = sum(1 for gram in query_trigrams if node_id in self.trigram_index.get(gram, []))
        total_query_grams = len(query_monograms) + len(query_bigrams) + len(query_trigrams)
        if total_query_grams > 0:
            score = (
                ngram_weights.monogram * monogram_matches +
                ngram_weights.bigram * bigram_matches +
                ngram_weights.trigram * trigram_matches
            ) / total_query_grams
        else:
            score = 0.0
        return score

    def _calculate_max_possible_score(self, query_monograms: List[str], query_bigrams: List[str], query_trigrams: List[str], ngram_weights: Optional[Any]) -> float:
        if ngram_weights is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                ngram_weights = DEFAULT_PARAMETERS.ngram_weights
            except Exception:
                @dataclass
                class FallbackNGramWeights:
                    monogram: float = 1.0
                    bigram: float = 4.0
                    trigram: float = 9.0
                ngram_weights = FallbackNGramWeights()
        total_query_grams = len(query_monograms) + len(query_bigrams) + len(query_trigrams)
        if total_query_grams > 0:
            return (
                ngram_weights.monogram * len(query_monograms) +
                ngram_weights.bigram * len(query_bigrams) +
                ngram_weights.trigram * len(query_trigrams)
            ) / total_query_grams
        return 1.0

    def calculate_normalized_lexical_similarity(self, query: str, parameters: Optional[Any] = None, node_ids: Optional[List[int]] = None) -> Dict[int, float]:
        tokens = self._tokenize_and_clean(query)
        query_monograms = tokens
        query_bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
        query_trigrams = [f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}" for i in range(len(tokens)-2)]
        ngram_weights = getattr(parameters, 'ngram_weights', None) if parameters is not None else getattr(self.parameters, 'ngram_weights', None)
        max_possible_score = self._calculate_max_possible_score(query_monograms, query_bigrams, query_trigrams, ngram_weights)

        if node_ids is None:
            relevant_nodes = set()
            for gram in query_monograms:
                relevant_nodes.update(self.monogram_index.get(gram, []))
            for gram in query_bigrams:
                relevant_nodes.update(self.bigram_index.get(gram, []))
            for gram in query_trigrams:
                relevant_nodes.update(self.trigram_index.get(gram, []))
        else:
            relevant_nodes = set(node_ids)

        scores: Dict[int, float] = {}
        for node_id in relevant_nodes:
            raw_score = self._calculate_node_score(node_id, query_monograms, query_bigrams, query_trigrams, ngram_weights)
            if raw_score > 0:
                normalized_score = min(raw_score / max_possible_score, 1.0) if max_possible_score > 0 else 0.0
                scores[node_id] = normalized_score
        return scores

    def calculate_lexical_similarity(self, query: str, parameters: Optional[Any] = None, node_ids: Optional[List[int]] = None) -> Dict[int, float]:
        """Calculate unnormalized lexical similarity between query and nodes."""
        tokens = self._tokenize_and_clean(query)
        query_monograms = tokens
        query_bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
        query_trigrams = [f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}" for i in range(len(tokens)-2)]
        ngram_weights = getattr(parameters, 'ngram_weights', None) if parameters is not None else getattr(self.parameters, 'ngram_weights', None)
        if node_ids is None:
            relevant_nodes = set()
            for gram in query_monograms:
                relevant_nodes.update(self.monogram_index.get(gram, []))
            for gram in query_bigrams:
                relevant_nodes.update(self.bigram_index.get(gram, []))
            for gram in query_trigrams:
                relevant_nodes.update(self.trigram_index.get(gram, []))
        else:
            relevant_nodes = set(node_ids)
        scores: Dict[int, float] = {}
        for node_id in relevant_nodes:
            score = self._calculate_node_score(node_id, query_monograms, query_bigrams, query_trigrams, ngram_weights)
            if score > 0:
                scores[node_id] = score
        return scores

    def get_matching_nodes(self, query: str, top_k: int = 10, normalize_scores: bool = True, parameters: Optional[Any] = None) -> List[Tuple[int, float]]:
        if normalize_scores:
            scores = self.calculate_normalized_lexical_similarity(query, parameters)
        else:
            # Fallback: unnormalized simple count
            tokens = self._tokenize_and_clean(query)
            query_monograms = tokens
            query_bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
            query_trigrams = [f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}" for i in range(len(tokens)-2)]
            ngram_weights = getattr(parameters, 'ngram_weights', None) if parameters is not None else getattr(self.parameters, 'ngram_weights', None)
            scores = {}
            relevant_nodes = set()
            for gram in query_monograms:
                relevant_nodes.update(self.monogram_index.get(gram, []))
            for gram in query_bigrams:
                relevant_nodes.update(self.bigram_index.get(gram, []))
            for gram in query_trigrams:
                relevant_nodes.update(self.trigram_index.get(gram, []))
            for node_id in relevant_nodes:
                s = self._calculate_node_score(node_id, query_monograms, query_bigrams, query_trigrams, ngram_weights)
                if s > 0:
                    scores[node_id] = s
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
