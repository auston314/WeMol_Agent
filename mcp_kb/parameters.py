"""
Configuration Parameters for Content Tree Search and Similarity Scoring

This module centralizes all weight control parameters used throughout the content tree
system for embedding similarity, n-gram scoring, and combined search ranking.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SemanticSimilarityWeights:
    """
    Weights for different embedding components in calculate_semantic_similarity function.
    
    These weights control how much each type of embedding contributes to the overall
    semantic similarity score between a query and a content node.
    """
    header: float = 0.2      # Weight for header embedding similarity
    summary: float = 0.2     # Weight for summary embedding similarity  
    content: float = 0.2     # Weight for content embedding similarity (legacy)
    chunks: float = 0.2      # Weight for chunk embedding similarity
    sentences: float = 0.2   # Weight for sentence embedding similarity
    
    def __post_init__(self):
        """Validate that weights sum to 1.0 or close to it."""
        total = self.header + self.summary + self.content + self.chunks + self.sentences
        if not (0.95 <= total <= 1.05):  # Allow small floating point differences
            print(f"Warning: Semantic similarity weights sum to {total:.3f}, not 1.0")


@dataclass
class NGramWeights:
    """
    Weights for different n-gram types in lexical similarity scoring.
    
    These weights control the importance of monogram, bigram, and trigram matches
    in the _calculate_node_score function of InverseIndexBuilder.
    """
    monogram: float = 1.0    # Weight for single word matches
    bigram: float = 4.0      # Weight for two-word phrase matches
    trigram: float = 9.0     # Weight for three-word phrase matches
    
    @property
    def max_possible_score_per_gram(self) -> float:
        """Calculate the maximum possible score per n-gram type."""
        return max(self.monogram, self.bigram, self.trigram)


@dataclass
class CombinedSearchWeights:
    """
    Weights for combining semantic and lexical scores in enhanced_search function.
    
    These weights control how much semantic similarity vs lexical similarity
    contributes to the final combined search ranking score.
    """
    semantic: float = 0.6    # Weight for semantic similarity score
    lexical: float = 0.4     # Weight for lexical similarity score
    
    def __post_init__(self):
        """Validate that weights sum to 1.0."""
        total = self.semantic + self.lexical
        if not (0.95 <= total <= 1.05):  # Allow small floating point differences
            print(f"Warning: Combined search weights sum to {total:.3f}, not 1.0")


@dataclass
class SearchParameters:
    """
    Comprehensive search parameters configuration.
    
    This class bundles all weight configurations together and provides
    convenient access to all search-related parameters.
    """
    semantic_weights: SemanticSimilarityWeights
    ngram_weights: NGramWeights
    combined_weights: CombinedSearchWeights
    
    # Search behavior parameters
    min_relevance_threshold: float = 0.01    # Minimum score to consider relevant
    default_max_results: int = 10            # Default number of search results
    
    def __init__(self, 
                 semantic_weights: Optional[SemanticSimilarityWeights] = None,
                 ngram_weights: Optional[NGramWeights] = None,
                 combined_weights: Optional[CombinedSearchWeights] = None):
        """
        Initialize search parameters with optional custom weights.
        
        Args:
            semantic_weights: Custom semantic similarity weights
            ngram_weights: Custom n-gram weights  
            combined_weights: Custom combined search weights
        """
        self.semantic_weights = semantic_weights or SemanticSimilarityWeights()
        self.ngram_weights = ngram_weights or NGramWeights()
        self.combined_weights = combined_weights or CombinedSearchWeights()


# Default parameter configurations
DEFAULT_PARAMETERS = SearchParameters()

# Alternative parameter configurations for different use cases

# Configuration emphasizing exact term matches
LEXICAL_FOCUSED_PARAMETERS = SearchParameters(
    semantic_weights=SemanticSimilarityWeights(
        header=0.3, summary=0.2, content=0.2, chunks=0.15, sentences=0.15
    ),
    combined_weights=CombinedSearchWeights(semantic=0.3, lexical=0.7)
)

# Configuration emphasizing semantic understanding
SEMANTIC_FOCUSED_PARAMETERS = SearchParameters(
    semantic_weights=SemanticSimilarityWeights(
        header=0.15, summary=0.15, content=0.15, chunks=0.25, sentences=0.3
    ),
    combined_weights=CombinedSearchWeights(semantic=0.8, lexical=0.2)
)

# Configuration for balanced search with emphasis on headers and summaries
STRUCTURED_CONTENT_PARAMETERS = SearchParameters(
    semantic_weights=SemanticSimilarityWeights(
        header=0.3, summary=0.3, content=0.1, chunks=0.15, sentences=0.15
    ),
    combined_weights=CombinedSearchWeights(semantic=0.6, lexical=0.4)
)

# Configuration emphasizing fine-grained content (sentences and chunks)
DETAILED_CONTENT_PARAMETERS = SearchParameters(
    semantic_weights=SemanticSimilarityWeights(
        header=0.1, summary=0.1, content=0.1, chunks=0.35, sentences=0.35
    ),
    combined_weights=CombinedSearchWeights(semantic=0.7, lexical=0.3)
)


def get_parameters(config_name: str = "default") -> SearchParameters:
    """
    Get a predefined parameter configuration by name.
    
    Args:
        config_name: Name of the configuration to retrieve
                    Options: "default", "lexical_focused", "semantic_focused", 
                            "structured_content", "detailed_content"
    
    Returns:
        SearchParameters: The requested parameter configuration
    
    Raises:
        ValueError: If config_name is not recognized
    """
    configs = {
        "default": DEFAULT_PARAMETERS,
        "lexical_focused": LEXICAL_FOCUSED_PARAMETERS,
        "semantic_focused": SEMANTIC_FOCUSED_PARAMETERS,
        "structured_content": STRUCTURED_CONTENT_PARAMETERS,
        "detailed_content": DETAILED_CONTENT_PARAMETERS
    }
    
    if config_name not in configs:
        available = ", ".join(configs.keys())
        raise ValueError(f"Unknown config '{config_name}'. Available: {available}")
    
    return configs[config_name]


def create_custom_parameters(semantic_header: float = 0.2,
                           semantic_summary: float = 0.2,
                           semantic_content: float = 0.2,
                           semantic_chunks: float = 0.2,
                           semantic_sentences: float = 0.2,
                           ngram_monogram: float = 1.0,
                           ngram_bigram: float = 4.0,
                           ngram_trigram: float = 9.0,
                           combined_semantic: float = 0.6,
                           combined_lexical: float = 0.4) -> SearchParameters:
    """
    Create a custom SearchParameters configuration with specified weights.
    
    Args:
        semantic_header: Weight for header embedding similarity
        semantic_summary: Weight for summary embedding similarity
        semantic_content: Weight for content embedding similarity
        semantic_chunks: Weight for chunk embedding similarity
        semantic_sentences: Weight for sentence embedding similarity
        ngram_monogram: Weight for monogram matches
        ngram_bigram: Weight for bigram matches
        ngram_trigram: Weight for trigram matches
        combined_semantic: Weight for semantic similarity in final score
        combined_lexical: Weight for lexical similarity in final score
    
    Returns:
        SearchParameters: Custom parameter configuration
    """
    return SearchParameters(
        semantic_weights=SemanticSimilarityWeights(
            header=semantic_header,
            summary=semantic_summary,
            content=semantic_content,
            chunks=semantic_chunks,
            sentences=semantic_sentences
        ),
        ngram_weights=NGramWeights(
            monogram=ngram_monogram,
            bigram=ngram_bigram,
            trigram=ngram_trigram
        ),
        combined_weights=CombinedSearchWeights(
            semantic=combined_semantic,
            lexical=combined_lexical
        )
    )


def print_parameters(params: SearchParameters) -> None:
    """
    Print a formatted summary of the search parameters.
    
    Args:
        params: SearchParameters to display
    """
    print("Search Parameters Configuration:")
    print("=" * 50)
    
    print("\nSemantic Similarity Weights:")
    print(f"  Header:    {params.semantic_weights.header:.2f}")
    print(f"  Summary:   {params.semantic_weights.summary:.2f}")
    print(f"  Content:   {params.semantic_weights.content:.2f}")
    print(f"  Chunks:    {params.semantic_weights.chunks:.2f}")
    print(f"  Sentences: {params.semantic_weights.sentences:.2f}")
    
    semantic_sum = (params.semantic_weights.header + 
                   params.semantic_weights.summary + 
                   params.semantic_weights.content + 
                   params.semantic_weights.chunks + 
                   params.semantic_weights.sentences)
    print(f"  Total:     {semantic_sum:.2f}")
    
    print("\nN-Gram Weights:")
    print(f"  Monogram:  {params.ngram_weights.monogram:.1f}")
    print(f"  Bigram:    {params.ngram_weights.bigram:.1f}")
    print(f"  Trigram:   {params.ngram_weights.trigram:.1f}")
    
    print("\nCombined Search Weights:")
    print(f"  Semantic:  {params.combined_weights.semantic:.2f}")
    print(f"  Lexical:   {params.combined_weights.lexical:.2f}")
    
    combined_sum = params.combined_weights.semantic + params.combined_weights.lexical
    print(f"  Total:     {combined_sum:.2f}")
    
    print(f"\nOther Parameters:")
    print(f"  Min Relevance Threshold: {params.min_relevance_threshold:.3f}")
    print(f"  Default Max Results:     {params.default_max_results}")


if __name__ == "__main__":
    # Example usage and testing
    print("Default Parameters:")
    print_parameters(DEFAULT_PARAMETERS)
    
    print("\n" + "="*70)
    print("Semantic Focused Parameters:")
    print_parameters(SEMANTIC_FOCUSED_PARAMETERS)
    
    print("\n" + "="*70)
    print("Custom Parameters Example:")
    custom = create_custom_parameters(
        semantic_header=0.4,
        semantic_summary=0.3,
        semantic_chunks=0.3,
        combined_semantic=0.8,
        combined_lexical=0.2
    )
    print_parameters(custom)
