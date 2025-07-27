# RAG Query Custom Parameters Enhancement

## Overview

The `rag_query` method in `ContentTree` has been enhanced to accept a `custom_params` parameter that provides comprehensive control over all weight parameters used during query processing.

## Changes Made

### Updated Method Signature

```python
def rag_query(self, user_query: str, top_k: int = 1, 
              llm_model: str = 'qwen2.5vl:32b',
              llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
              semantic_weight: Optional[float] = None, 
              lexical_weight: Optional[float] = None,
              custom_params: Optional[Any] = None,
              debug: bool = False) -> str:
```

### Key Enhancements

1. **Custom Parameters Support**: Added `custom_params` parameter that accepts a `SearchParameters` object from `parameters.py`

2. **Parameter Precedence Logic**: Implemented intelligent parameter handling with the following precedence:
   - `custom_params` (highest priority)
   - Individual `semantic_weight`/`lexical_weight` parameters 
   - Default parameters from `parameters.py`
   - Hardcoded fallback values (lowest priority)

3. **Backward Compatibility**: Maintained full backward compatibility with existing code using individual weight parameters

4. **Enhanced Parameter Passing**: The method now passes the full `parameters` object to `enhanced_search()`, enabling control of semantic similarity component weights

## Usage Examples

### Using Predefined Configurations

```python
from content_tree import ContentTree
from parameters import DEFAULT_PARAMETERS, SEMANTIC_FOCUSED_PARAMETERS, LEXICAL_FOCUSED_PARAMETERS

tree = ContentTree()

# Use default balanced parameters
result1 = tree.rag_query("What is atomic structure?", custom_params=DEFAULT_PARAMETERS)

# Use semantic-focused search (80% semantic, 20% lexical)
result2 = tree.rag_query("What is atomic structure?", custom_params=SEMANTIC_FOCUSED_PARAMETERS)

# Use lexical-focused search (30% semantic, 70% lexical)
result3 = tree.rag_query("What is atomic structure?", custom_params=LEXICAL_FOCUSED_PARAMETERS)
```

### Using Custom Parameters

```python
from parameters import create_custom_parameters

# Create custom configuration
custom_config = create_custom_parameters(
    # Semantic similarity weights (must sum to ~1.0)
    semantic_header=0.3,     # Emphasize header matching
    semantic_summary=0.3,    # Emphasize summary matching  
    semantic_content=0.1,    # De-emphasize content matching
    semantic_chunks=0.2,     # Moderate chunk matching
    semantic_sentences=0.1,  # De-emphasize sentence matching
    
    # N-gram weights for lexical similarity
    ngram_monogram=0.5,      # Lower weight for single words
    ngram_bigram=2.0,        # Moderate weight for word pairs
    ngram_trigram=4.5,       # Higher weight for phrases
    
    # Combined search weights (must sum to ~1.0)
    combined_semantic=0.7,   # Prefer semantic similarity
    combined_lexical=0.3     # Lesser weight for lexical similarity
)

result = tree.rag_query("What is atomic structure?", custom_params=custom_config)
```

### Backward Compatibility

```python
# Still works - individual parameters override defaults
result = tree.rag_query(
    "What is atomic structure?", 
    semantic_weight=0.8, 
    lexical_weight=0.2
)
```

## Parameter Control Scope

The `custom_params` parameter controls:

1. **Semantic Similarity Weights** (in `calculate_semantic_similarity`):
   - Header embedding contribution
   - Summary embedding contribution
   - Content embedding contribution
   - Chunk embeddings contribution
   - Sentence embeddings contribution

2. **N-gram Weights** (in `InverseIndexBuilder._calculate_node_score`):
   - Monogram (single word) match weights
   - Bigram (two-word phrase) match weights
   - Trigram (three-word phrase) match weights

3. **Combined Search Weights** (in `enhanced_search`):
   - Semantic similarity contribution to final score
   - Lexical similarity contribution to final score

## Benefits

1. **Flexible Configuration**: Different search scenarios can use different parameter sets
2. **Easy Experimentation**: Researchers can quickly test different weight combinations
3. **Backward Compatibility**: Existing code continues to work without changes
4. **Centralized Control**: All parameters managed through the `parameters.py` system
5. **Consistent Behavior**: Same parameter object controls weights across all search components

## Testing

The functionality has been tested with:
- All predefined parameter configurations
- Custom parameter creation and usage
- Backward compatibility scenarios
- Parameter weight verification
- Edge cases and error handling

All tests pass successfully, confirming proper integration and functionality.
