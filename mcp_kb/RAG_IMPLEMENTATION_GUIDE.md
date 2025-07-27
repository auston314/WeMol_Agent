# RAG (Retrieval-Augmented Generation) Implementation

## Overview

This document describes the RAG functionality implemented in the ContentTree system for answering user queries about chemistry concepts using textbook content.

## How RAG Works

The RAG system combines **information retrieval** with **text generation** to provide accurate answers to user questions:

1. **Query Processing**: User asks a question
2. **Information Retrieval**: System finds relevant content using enhanced search
3. **Context Assembly**: Relevant content is collected and formatted
4. **Answer Generation**: LLM generates an answer based on the retrieved content
5. **Quality Control**: System validates the answer and handles cases with insufficient information

## Implementation Details

### Main Function: `rag_query()`

```python
def rag_query(self, user_query: str, top_k: int = 1, 
              llm_model: str = 'qwen2.5vl:32b',
              llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
              semantic_weight: float = 0.6, lexical_weight: float = 0.4) -> str
```

**Parameters:**
- `user_query`: The user's question
- `top_k`: Number of top relevant nodes to use for context (default: 1)
- `llm_model`: LLM model for answer generation
- `llm_api_url`: API URL for the LLM service
- `semantic_weight`: Weight for semantic similarity (future use)
- `lexical_weight`: Weight for lexical similarity

**Returns:**
- Generated answer string
- "No information in the provided content for your query" if no relevant content found

### Key Features

#### 1. Enhanced Search Integration
- Uses the `enhanced_search()` method with normalized n-gram scoring
- Combines lexical similarity for accurate content retrieval
- Filters results with relevance scores > 0.01

#### 2. Content Assembly
- Collects content from top-k most relevant nodes
- Includes node headers for context
- Adds summaries when available and distinct from main content
- Formats content with clear section separators

#### 3. Answer Generation
- Uses ContentProcessor for LLM interaction
- Comprehensive prompt with clear instructions
- Temperature set to 0.2 for consistent, factual responses
- Maximum 512 tokens for concise answers

#### 4. Quality Control
- Checks for "no information" indicators in LLM responses
- Validates answer length (minimum 20 characters)
- Graceful error handling with fallback responses

## Usage Examples

### Basic Usage

```python
from content_tree import ContentTree

# Initialize and build tree
tree = ContentTree()
tree.build_textbook_tree("/path/to/md_files")
tree.process_tree_content(create_inverse_index=True)

# Ask a question
answer = tree.rag_query("What are the phases of matter?")
print(answer)
```

### Advanced Usage with Multiple Nodes

```python
# Use top-3 nodes for more comprehensive context
answer = tree.rag_query(
    "What is the scientific method?", 
    top_k=3,
    semantic_weight=0.7,
    lexical_weight=0.3
)
```

## Test Results

### Successful Queries
✅ **"What are the phases of matter?"**
- Found relevant content in "1.2 Phases and Classification of Matter"
- Generated accurate answer describing solid, liquid, gas, and plasma phases

✅ **"How do you calculate significant figures?"**
- Retrieved calculation examples and rules
- Provided step-by-step instructions with examples

✅ **"What are atoms and molecules?"**
- Found definitions in "Atoms and Molecules" section
- Generated clear explanations with distinctions

✅ **"How do you perform dimensional analysis?"**
- Retrieved methodology from textbook examples
- Provided structured approach with sample calculation

### Handled Edge Cases
❌ **"What is quantum mechanics?"** → "No information in the provided content for your query"
❌ **"How do you build a rocket?"** → "No information in the provided content for your query"

## Architecture Benefits

### 1. Modular Design
- RAG function integrates seamlessly with existing ContentTree
- Leverages existing search and content processing infrastructure
- Reuses ContentProcessor for consistent LLM interactions

### 2. Scalable Retrieval
- N-gram indexing provides fast, accurate content matching
- Normalized scoring ensures fair relevance ranking
- Configurable top-k allows balancing context vs. focus

### 3. Quality Assurance
- Multiple validation layers prevent hallucination
- Clear fallback behavior for out-of-scope queries
- Consistent "No information" responses when appropriate

### 4. Extensible Framework
- Easy to add semantic similarity when embeddings are available
- Configurable LLM parameters for different use cases
- Support for different content types and domains

## Performance Characteristics

### Strengths
- **High Accuracy**: Answers are grounded in actual textbook content
- **Fast Retrieval**: N-gram indexing provides sub-second search
- **Reliable Fallback**: Gracefully handles out-of-scope questions
- **Contextual Answers**: Uses relevant section headers and summaries

### Current Limitations
- Limited to Chapter 1 content (first 3 files in current implementation)
- No semantic similarity yet (embedding-based search not implemented)
- Single-domain focus (chemistry textbook only)

### Future Enhancements
- Add semantic similarity using embeddings
- Expand to full textbook content
- Multi-modal support for figures and equations
- Citation tracking for transparency

## Error Handling

The RAG system includes comprehensive error handling:

1. **Empty Queries**: Returns "Please provide a valid query"
2. **No Search Results**: Returns standard "No information" message
3. **Low Relevance**: Filters out results with score ≤ 0.01
4. **LLM Errors**: Falls back to "No information" message
5. **System Errors**: Logs error and returns fallback response

## Integration with Existing System

The RAG functionality builds on the existing ContentTree infrastructure:

- **Content Processing**: Uses existing summary/keyword generation
- **Search Infrastructure**: Leverages InverseIndexBuilder with n-gram support
- **LLM Integration**: Reuses ContentProcessor for consistent API calls
- **Tree Structure**: Works with existing hierarchical content organization

This ensures consistency with the existing codebase while adding powerful Q&A capabilities.

## Demo Scripts

Two demonstration scripts are provided:

1. **`test_rag_functionality.py`**: Comprehensive testing with multiple queries
2. **`demo_rag.py`**: Interactive demo for hands-on exploration

These scripts showcase the RAG system's capabilities and provide examples for integration into other applications.
