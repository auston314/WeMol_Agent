"""
Content Processing and Analysis Utilities for ContentTree

This module provides comprehensive text processing, embedding generation, 
and lexical analysis capabilities for ContentNode objects.
"""

import re
import json
import time
import requests
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict, Counter
import numpy as np
from dataclasses import dataclass
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from openai import OpenAI

# Download required NLTK data if not already present
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')

# Get English stopwords
STOP_WORDS = set(stopwords.words('english'))

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
    
    def __init__(self, llm_model: str = 'qwen2.5vl:32b', 
                 llm_api_url: str = 'https://chatmol.org/ollama/api/generate'):
        self.llm_model = llm_model
        self.llm_api_url = llm_api_url
    
    def generate_content_summary(self, content_text: str, max_words: int = 30) -> str:
        """
        Generate a summary of the content text using LLM.
        
        Args:
            content_text (str): Text to summarize
            max_words (int): Maximum words in summary
            
        Returns:
            str: Generated summary
        """
        content_text = content_text.strip()
        if not content_text:
            return ""
        
        print("Generating summary...")
        summary_prompt = (
            f"Please generate a summary of the following text in triple backticks "
            f"in no more than {max_words} words. Keep summary clean, "
            f"no title or header is needed.\n"
        )
        summary = self._call_llm_with_template(content_text, summary_prompt)
        return summary.strip()
    
    def generate_keyword_list(self, content_text: str, max_keywords: int = 10) -> List[str]:
        """
        Generate a list of keywords from the content text using LLM.
        
        Args:
            content_text (str): Text to extract keywords from
            max_keywords (int): Maximum number of keywords
            
        Returns:
            List[str]: List of keywords
        """
        content_text = content_text.strip()
        if not content_text:
            return []
        
        print("Generating keywords...")
        keyword_prompt = (
            f"Generate a list of keywords of the following text in triple backticks "
            f"in no more than {max_keywords} words. The keyword list should be in "
            f"JSON list format. Only list the most important keywords. "
            f"Make your response clean, no title or header is needed.\n"
        )
        keywords_response = self._call_llm_with_template(content_text, keyword_prompt)
        
        try:
            keywords = json.loads(keywords_response)
            return keywords if isinstance(keywords, list) else []
        except json.JSONDecodeError:
            # Fallback: extract words from response
            words = re.findall(r'\b[a-zA-Z]+\b', keywords_response)
            return words[:max_keywords]
    
    def create_content_chunks(self, content_text: str) -> List[ContentChunk]:
        """
        Split content into chunks by type (paragraphs, tables, figures, code blocks).
        
        Args:
            content_text (str): Text to chunk
            
        Returns:
            List[ContentChunk]: List of content chunks
        """
        if not content_text.strip():
            return []
        
        chunks = []
        
        # First, find figure chunks (image link + caption)
        figure_blocks = self._find_figure_blocks(content_text)
        
        # Patterns for other content types
        patterns = {
            'code': r'```[\s\S]*?```',
            'pre-formatted': r'<pre>[\s\S]*?</pre>',
            'table': r'(?:\|.*?\|\n)+',
        }
        
        # Find all special content blocks
        special_blocks = []
        
        # Add figure blocks
        for figure_block in figure_blocks:
            special_blocks.append(figure_block)
        
        # Add other content blocks
        for block_type, pattern in patterns.items():
            for match in re.finditer(pattern, content_text):
                # Check if this match overlaps with any figure block
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
        
        # Sort by position
        special_blocks.sort(key=lambda x: x['start'])
        
        # Extract content between special blocks as paragraphs
        last_end = 0
        for block in special_blocks:
            # Add paragraph content before this block
            if block['start'] > last_end:
                paragraph_text = content_text[last_end:block['start']].strip()
                if paragraph_text:
                    # Split by double newlines for multiple paragraphs
                    paragraphs = re.split(r'\n\s*\n', paragraph_text)
                    for para in paragraphs:
                        para = para.strip()
                        if para:
                            chunks.append(ContentChunk(
                                content=para,
                                chunk_type='paragraph',
                                sentences=[],
                                word_count=0
                            ))
            
            # Add the special block
            chunks.append(ContentChunk(
                content=block['content'],
                chunk_type=block['type'],
                sentences=[],
                word_count=0
            ))
            
            last_end = block['end']
        
        # Add remaining content as paragraphs
        if last_end < len(content_text):
            remaining_text = content_text[last_end:].strip()
            if remaining_text:
                paragraphs = re.split(r'\n\s*\n', remaining_text)
                for para in paragraphs:
                    para = para.strip()
                    if para:
                        chunks.append(ContentChunk(
                            content=para,
                            chunk_type='paragraph',
                            sentences=[],
                            word_count=0
                        ))
        
        return chunks
    
    def _find_figure_blocks(self, content_text: str) -> List[Dict]:
        """
        Find figure blocks that include both image links and their captions.
        
        A figure block consists of:
        1. An image markdown link: ![alt text](image_path)
        2. Followed by a figure caption (typically starting with "Figure")
        
        Args:
            content_text (str): Text content to search
            
        Returns:
            List[Dict]: List of figure block dictionaries with start, end, type, and content
        """
        figure_blocks = []
        
        # Pattern to match image markdown links
        image_pattern = r'!\[.*?\]\([^)]+\)'
        
        for match in re.finditer(image_pattern, content_text):
            image_start = match.start()
            image_end = match.end()
            image_content = match.group()
            
            # Look for caption after the image
            # Caption typically starts after some whitespace and may begin with "Figure"
            remaining_text = content_text[image_end:]
            
            # Find the caption - look for text until the next paragraph break or another special block
            caption_match = re.match(r'\s*\n?\s*(Figure\s+[\d.]+[^\n]*(?:\n(?!\s*\n)[^\n]*)*)', remaining_text, re.IGNORECASE)
            
            if caption_match:
                # Found a figure caption
                caption_content = caption_match.group(1).strip()
                caption_end = image_end + caption_match.end()
                
                full_figure_content = content_text[image_start:caption_end]
                
                figure_blocks.append({
                    'start': image_start,
                    'end': caption_end,
                    'type': 'figure',
                    'content': full_figure_content
                })
            else:
                # No caption found, but still treat as figure (image only)
                # Look ahead to see if there's any text that could be a caption
                # Even without "Figure" prefix
                caption_match = re.match(r'\s*\n?\s*([^\n]+(?:\n(?!\s*\n)[^\n]*)*)', remaining_text)
                
                if caption_match:
                    potential_caption = caption_match.group(1).strip()
                    # Check if this looks like a caption (not too short, not starting with markdown symbols)
                    if (len(potential_caption) > 20 and 
                        not potential_caption.startswith(('!', '#', '```', '|')) and
                        not re.match(r'^\s*$', potential_caption)):
                        
                        caption_end = image_end + caption_match.end()
                        full_figure_content = content_text[image_start:caption_end]
                        
                        figure_blocks.append({
                            'start': image_start,
                            'end': caption_end,
                            'type': 'figure',
                            'content': full_figure_content
                        })
                    else:
                        # Just the image without caption
                        figure_blocks.append({
                            'start': image_start,
                            'end': image_end,
                            'type': 'figure',
                            'content': image_content
                        })
                else:
                    # Just the image without caption
                    figure_blocks.append({
                        'start': image_start,
                        'end': image_end,
                        'type': 'figure',
                        'content': image_content
                    })
        
        return figure_blocks
    
    def extract_sentences_from_content(self, content_text: str) -> List[str]:
        """
        Extract individual sentences from content text.
        
        Args:
            content_text (str): Text to extract sentences from
            
        Returns:
            List[str]: List of sentences
        """
        if not content_text.strip():
            return []
        
        return extract_sentences_from_text(content_text)
    
    def _call_llm_with_template(self, input_text: str, prompt_template: str) -> str:
        """
        Helper function to call LLM API with a specific prompt template.
        
        Args:
            input_text (str): The input text
            prompt_template (str): The prompt template
            
        Returns:
            str: Generated response text
        """
        prompt = prompt_template + f"```{input_text}```"
        return self._call_llm_service(prompt)
    
    def _call_llm_service(self, prompt: str, temperature: float = 0.1, 
                         max_tokens: int = 1024) -> str:
        """
        Helper function to call LLM API and generate text.
        
        Args:
            prompt (str): The input prompt
            temperature (float): Sampling temperature
            max_tokens (int): Maximum number of tokens
            
        Returns:
            str: Generated response text
        """
        payload = {
            'model': self.llm_model,
            'prompt': prompt,
            'temperature': temperature,
            'max_tokens': max_tokens
        }

        try:
            response = requests.post(self.llm_api_url, json=payload, stream=True)
            
            generated_text = ''
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line.decode('utf-8'))
                        if 'response' in data:
                            generated_text += data['response']
            else:
                print(f'LLM API Error: {response.status_code}, {response.text}')
                
            return generated_text
        except Exception as e:
            print(f"Error calling LLM service: {e}")
            return ""


class EmbeddingGenerator:
    """Handles embedding generation for different types of content."""
    
    def __init__(self, model: str = "text-embedding-3-large", batch_size: int = 32):
        self.model = model
        self.batch_size = batch_size
        self.client = OpenAI()
    
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts (List[str]): List of texts to embed
            
        Returns:
            np.ndarray: Array of embeddings
        """
        if not texts:
            return np.array([])
        
        # Clean texts
        cleaned_texts = [text.replace("\n", " ").strip() for text in texts if text.strip()]
        if not cleaned_texts:
            return np.array([])
        
        embeddings = []
        n_batches = (len(cleaned_texts) + self.batch_size - 1) // self.batch_size
        
        print(f"Generating embeddings for {len(cleaned_texts)} texts in {n_batches} batches...")
        
        for i in range(n_batches):
            start_idx = i * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(cleaned_texts))
            batch_texts = cleaned_texts[start_idx:end_idx]
            
            try:
                response = self.client.embeddings.create(
                    input=batch_texts, 
                    model=self.model
                )
                batch_embeddings = [d.embedding for d in response.data]
                embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"Error generating embeddings for batch {i+1}: {e}")
                # Add zero embeddings for failed batch
                embedding_dim = 3072 if "large" in self.model else 1536
                zero_embeddings = [[0.0] * embedding_dim] * len(batch_texts)
                embeddings.extend(zero_embeddings)
        
        return np.array(embeddings)
    
    def generate_header_embedding(self, header: str) -> Optional[np.ndarray]:
        """Generate embedding for a node header."""
        if not header or header.strip() in ["", "Root"]:
            return None
        embeddings = self.generate_embeddings([header])
        return embeddings[0] if len(embeddings) > 0 else None
    
    def generate_summary_embedding(self, summary: str) -> Optional[np.ndarray]:
        """Generate embedding for a node summary."""
        if not summary or not summary.strip():
            return None
        embeddings = self.generate_embeddings([summary])
        return embeddings[0] if len(embeddings) > 0 else None
    
    def generate_chunk_embeddings(self, chunks: List[ContentChunk]) -> np.ndarray:
        """Generate embeddings for content chunks."""
        if not chunks:
            return np.array([])
        
        chunk_texts = [chunk.content for chunk in chunks if chunk.content.strip()]
        return self.generate_embeddings(chunk_texts)
    
    def generate_sentence_embeddings(self, sentences: List[str]) -> np.ndarray:
        """Generate embeddings for individual sentences."""
        if not sentences:
            return np.array([])
        
        valid_sentences = [sent for sent in sentences if sent.strip()]
        return self.generate_embeddings(valid_sentences)


class InverseIndexBuilder:
    """Builds and manages inverse indexes for n-grams."""
    
    def __init__(self, include_stopwords: bool = False, parameters: Optional[Any] = None):
        self.include_stopwords = include_stopwords
        self.monogram_index: Dict[str, List[int]] = defaultdict(list)
        self.bigram_index: Dict[str, List[int]] = defaultdict(list)
        self.trigram_index: Dict[str, List[int]] = defaultdict(list)
        
        # Store parameters for n-gram weights
        if parameters is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                self.parameters = DEFAULT_PARAMETERS
            except ImportError:
                # Fallback if parameters.py is not available
                from dataclasses import dataclass
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
        """
        Build n-gram indexes for all nodes.
        
        Args:
            nodes (List[ContentNode]): List of content nodes to index
        """
        print("Building n-gram indexes...")
        
        for node in nodes:
            if hasattr(node, 'content_text') and node.content_text:
                self._add_node_to_indexes(node.node_id, node.content_text)
        
        print(f"Index stats: {len(self.monogram_index)} monograms, "
              f"{len(self.bigram_index)} bigrams, {len(self.trigram_index)} trigrams")
    
    def _add_node_to_indexes(self, node_id: int, content_text: str) -> None:
        """Add a single node's content to the indexes."""
        # Clean and tokenize text
        tokens = self._tokenize_and_clean(content_text)
        
        if not tokens:
            return
        
        # Build n-grams
        monograms = tokens
        bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
        trigrams = [f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}" for i in range(len(tokens)-2)]
        
        # Add to indexes
        for gram in monograms:
            if node_id not in self.monogram_index[gram]:
                self.monogram_index[gram].append(node_id)
        
        for gram in bigrams:
            if node_id not in self.bigram_index[gram]:
                self.bigram_index[gram].append(node_id)
        
        for gram in trigrams:
            if node_id not in self.trigram_index[gram]:
                self.trigram_index[gram].append(node_id)
    
    def _tokenize_and_clean(self, text: str) -> List[str]:
        """Tokenize text and remove stopwords if configured."""
        # Convert to lowercase and tokenize
        tokens = word_tokenize(text.lower())
        
        # Remove punctuation and non-alphabetic tokens
        tokens = [token for token in tokens if token.isalpha()]
        
        # Remove stopwords if configured
        if not self.include_stopwords:
            tokens = [token for token in tokens if token not in STOP_WORDS]
        
        return tokens
    
    def calculate_lexical_similarity(self, query: str, parameters: Optional[Any] = None, node_ids: List[int] = None) -> Dict[int, float]:
        """
        Calculate lexical similarity scores between query and nodes.
        
        Args:
            query (str): Query text
            parameters: Parameters object from parameters.py (optional)
            node_ids (List[int], optional): Specific node IDs to score. If None, scores all nodes.
            
        Returns:
            Dict[int, float]: Dictionary mapping node_id to similarity score
        """
        query_tokens = self._tokenize_and_clean(query)
        query_monograms = query_tokens
        query_bigrams = [f"{query_tokens[i]} {query_tokens[i+1]}" 
                        for i in range(len(query_tokens)-1)]
        query_trigrams = [f"{query_tokens[i]} {query_tokens[i+1]} {query_tokens[i+2]}" 
                         for i in range(len(query_tokens)-2)]
        
        # Use provided parameters or fall back to instance parameters
        ngram_weights = None
        if parameters is not None:
            ngram_weights = getattr(parameters, 'ngram_weights', None)
        if ngram_weights is None:
            ngram_weights = getattr(self.parameters, 'ngram_weights', None)
        
        # Collect all relevant node IDs
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
        
        # Calculate scores
        scores = {}
        for node_id in relevant_nodes:
            score = self._calculate_node_score(
                node_id, query_monograms, query_bigrams, query_trigrams, ngram_weights
            )
            if score > 0:
                scores[node_id] = score
        
        return scores
    
    def _calculate_node_score(self, node_id: int, query_monograms: List[str], 
                            query_bigrams: List[str], query_trigrams: List[str],
                            ngram_weights: Optional[Any] = None) -> float:
        """
        Calculate the lexical similarity score for a specific node.
        
        Args:
            node_id: ID of the node to score
            query_monograms: List of query monograms
            query_bigrams: List of query bigrams  
            query_trigrams: List of query trigrams
            ngram_weights: NGramWeights object from parameters.py (optional)
            
        Returns:
            float: Lexical similarity score
        """
        # Get weights from parameters if not provided
        if ngram_weights is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                ngram_weights = DEFAULT_PARAMETERS.ngram_weights
            except ImportError:
                # Fallback to hardcoded defaults if parameters.py is not available
                from dataclasses import dataclass
                @dataclass
                class FallbackNGramWeights:
                    monogram: float = 1.0
                    bigram: float = 4.0
                    trigram: float = 9.0
                ngram_weights = FallbackNGramWeights()
        
        score = 0.0
        
        # Count matches for each n-gram type
        monogram_matches = sum(1 for gram in query_monograms 
                              if node_id in self.monogram_index.get(gram, []))
        bigram_matches = sum(1 for gram in query_bigrams 
                            if node_id in self.bigram_index.get(gram, []))
        trigram_matches = sum(1 for gram in query_trigrams 
                             if node_id in self.trigram_index.get(gram, []))
        
        # Calculate weighted score
        total_query_grams = len(query_monograms) + len(query_bigrams) + len(query_trigrams)
        if total_query_grams > 0:
            score = (
                ngram_weights.monogram * monogram_matches +
                ngram_weights.bigram * bigram_matches +
                ngram_weights.trigram * trigram_matches
            ) / total_query_grams
        
        return score
    
    def _calculate_max_possible_score(self, query_monograms: List[str], 
                                    query_bigrams: List[str], query_trigrams: List[str],
                                    ngram_weights: Optional[Any] = None) -> float:
        """
        Calculate the maximum possible n-gram score for a query.
        This represents the score if all query n-grams were perfectly matched.
        
        Args:
            query_monograms (List[str]): Query monograms
            query_bigrams (List[str]): Query bigrams  
            query_trigrams (List[str]): Query trigrams
            ngram_weights: NGramWeights object from parameters.py (optional)
            
        Returns:
            float: Maximum possible score for this query
        """
        # Get weights from parameters if not provided
        if ngram_weights is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                ngram_weights = DEFAULT_PARAMETERS.ngram_weights
            except ImportError:
                # Fallback to hardcoded defaults if parameters.py is not available
                from dataclasses import dataclass
                @dataclass
                class FallbackNGramWeights:
                    monogram: float = 1.0
                    bigram: float = 4.0
                    trigram: float = 9.0
                ngram_weights = FallbackNGramWeights()
        
        # Calculate maximum score assuming all n-grams match perfectly
        total_query_grams = len(query_monograms) + len(query_bigrams) + len(query_trigrams)
        if total_query_grams > 0:
            max_score = (
                ngram_weights.monogram * len(query_monograms) +
                ngram_weights.bigram * len(query_bigrams) +
                ngram_weights.trigram * len(query_trigrams)
            ) / total_query_grams
        else:
            max_score = 1.0  # Avoid division by zero
        
        return max_score
    
    def calculate_normalized_lexical_similarity(self, query: str, parameters: Optional[Any] = None, node_ids: List[int] = None) -> Dict[int, float]:
        """
        Calculate normalized lexical similarity scores between query and nodes.
        Scores are normalized to 0-1.0 range based on the maximum possible score for the query.
        
        Args:
            query (str): Query text
            parameters: Parameters object from parameters.py (optional)
            node_ids (List[int], optional): Specific node IDs to score. If None, scores all nodes.
            
        Returns:
            Dict[int, float]: Dictionary mapping node_id to normalized similarity score (0-1.0)
        """
        query_tokens = self._tokenize_and_clean(query)
        query_monograms = query_tokens
        query_bigrams = [f"{query_tokens[i]} {query_tokens[i+1]}" 
                        for i in range(len(query_tokens)-1)]
        query_trigrams = [f"{query_tokens[i]} {query_tokens[i+1]} {query_tokens[i+2]}" 
                         for i in range(len(query_tokens)-2)]
        
        # Use provided parameters or fall back to instance parameters
        ngram_weights = None
        if parameters is not None:
            ngram_weights = getattr(parameters, 'ngram_weights', None)
        if ngram_weights is None:
            ngram_weights = getattr(self.parameters, 'ngram_weights', None)
        
        # Calculate maximum possible score for normalization
        max_possible_score = self._calculate_max_possible_score(query_monograms, query_bigrams, query_trigrams, ngram_weights)
        
        # Collect all relevant node IDs
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
        
        # Calculate and normalize scores
        scores = {}
        for node_id in relevant_nodes:
            raw_score = self._calculate_node_score(
                node_id, query_monograms, query_bigrams, query_trigrams, ngram_weights
            )
            if raw_score > 0:
                # Normalize score to 0-1.0 range
                normalized_score = min(raw_score / max_possible_score, 1.0) if max_possible_score > 0 else 0.0
                scores[node_id] = normalized_score
        
        return scores
    
    def get_matching_nodes(self, query: str, top_k: int = 10, normalize_scores: bool = True, parameters: Optional[Any] = None) -> List[Tuple[int, float]]:
        """
        Get top-k nodes that match the query based on lexical similarity.
        
        Args:
            query (str): Query text
            top_k (int): Number of top results to return
            normalize_scores (bool): Whether to normalize scores to 0-1.0 range
            parameters: Parameters object from parameters.py (optional)
            
        Returns:
            List[Tuple[int, float]]: List of (node_id, score) tuples sorted by score
        """
        if normalize_scores:
            scores = self.calculate_normalized_lexical_similarity(query, parameters)
        else:
            scores = self.calculate_lexical_similarity(query, parameters)
        
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]


# Utility functions
def extract_sentences_from_text(text: str) -> List[str]:
    """Extract sentences from text using NLTK sentence tokenizer."""
    if not text.strip():
        return []
    
    try:
        sentences = sent_tokenize(text)
        # Clean sentences
        cleaned_sentences = []
        for sent in sentences:
            sent = sent.strip()
            if sent and len(sent) > 10:  # Filter out very short sentences
                cleaned_sentences.append(sent)
        return cleaned_sentences
    except Exception as e:
        print(f"Error tokenizing sentences: {e}")
        # Fallback to simple regex-based sentence splitting
        sentences = re.split(r'[.!?]+\s+', text)
        return [sent.strip() for sent in sentences if sent.strip() and len(sent.strip()) > 10]


def calculate_semantic_similarity(query_embedding: np.ndarray, 
                                content_embeddings: Optional[np.ndarray],
                                header_embedding: Optional[np.ndarray],
                                summary_embedding: Optional[np.ndarray],
                                chunk_embeddings: Optional[np.ndarray] = None,
                                sentence_embeddings: Optional[np.ndarray] = None,
                                weights: Optional[Any] = None) -> float:
    """
    Calculate semantic similarity score between query and node content.
    
    Args:
        query_embedding: Query embedding vector
        content_embeddings: Content embeddings
        header_embedding: Header embedding
        summary_embedding: Summary embedding
        chunk_embeddings: Chunk embeddings
        sentence_embeddings: Sentence embeddings
        weights: SemanticSimilarityWeights object from parameters.py (optional)
        
    Returns:
        float: Similarity score
    """
    # Import weights if not provided
    if weights is None:
        try:
            from parameters import DEFAULT_PARAMETERS
            weights = DEFAULT_PARAMETERS.semantic_weights
        except ImportError:
            # Fallback to hardcoded defaults if parameters.py is not available
            from dataclasses import dataclass
            @dataclass
            class FallbackWeights:
                header: float = 0.2
                summary: float = 0.2
                content: float = 0.2
                chunks: float = 0.2
                sentences: float = 0.2
            weights = FallbackWeights()
    
    total_score = 0.0
    total_weight = 0.0
    
    # Header similarity
    if header_embedding is not None:
        header_sim = np.dot(query_embedding, header_embedding)
        total_score += weights.header * header_sim
        total_weight += weights.header
    
    # Summary similarity
    if summary_embedding is not None:
        summary_sim = np.dot(query_embedding, summary_embedding)
        total_score += weights.summary * summary_sim
        total_weight += weights.summary
    
    # Content similarity (legacy support)
    if content_embeddings is not None:
        if content_embeddings.ndim == 1:
            content_sim = np.dot(query_embedding, content_embeddings)
        else:
            content_sim = np.max(np.dot(query_embedding, content_embeddings.T))
        total_score += weights.content * content_sim
        total_weight += weights.content
    
    # Chunk similarity (using maximum similarity across all chunks)
    if chunk_embeddings is not None and len(chunk_embeddings) > 0:
        if chunk_embeddings.ndim == 1:
            # Single chunk embedding
            chunk_sim = np.dot(query_embedding, chunk_embeddings)
        else:
            # Multiple chunk embeddings - use maximum similarity
            chunk_sim = np.max(np.dot(query_embedding, chunk_embeddings.T))
        total_score += weights.chunks * chunk_sim
        total_weight += weights.chunks
    
    # Sentence similarity (using maximum similarity across all sentences)
    if sentence_embeddings is not None and len(sentence_embeddings) > 0:
        if sentence_embeddings.ndim == 1:
            # Single sentence embedding
            sentence_sim = np.dot(query_embedding, sentence_embeddings)
        else:
            # Multiple sentence embeddings - use maximum similarity
            sentence_sim = np.max(np.dot(query_embedding, sentence_embeddings.T))
        total_score += weights.sentences * sentence_sim
        total_weight += weights.sentences
    
    return total_score / total_weight if total_weight > 0 else 0.0


class ContentEnhancer:
    """Main class that coordinates all content enhancement operations."""
    
    def __init__(self, llm_model: str = 'qwen2.5vl:32b', 
                 llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                 embedding_model: str = "text-embedding-3-large",
                 parameters: Optional[Any] = None):
        self.processor = ContentProcessor(llm_model, llm_api_url)
        self.embedding_generator = EmbeddingGenerator(embedding_model)
        self.index_builder = InverseIndexBuilder(parameters=parameters)
        
        # Store parameters for search operations
        if parameters is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                self.parameters = DEFAULT_PARAMETERS
            except ImportError:
                self.parameters = None
        else:
            self.parameters = parameters
    
    def enhance_content_tree(self, content_tree) -> None:
        """
        Enhance all nodes in the content tree with processed content and embeddings.
        
        Args:
            content_tree: ContentTree object to enhance
        """
        print("Enhancing content tree...")
        
        # Get all nodes except root
        all_nodes = content_tree.tree_node_iterator()
        content_nodes = [node for node in all_nodes if node.header_level > 0]
        
        # Process content for each node
        print(f"Processing {len(content_nodes)} nodes...")
        for i, node in enumerate(content_nodes, 1):
            print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
            self._enhance_single_node(node)
        
        # Build n-gram indexes
        self.index_builder.build_ngram_indexes(content_nodes)
        
        print("Content tree enhancement complete!")
    
    def _enhance_single_node(self, node) -> None:
        """Enhance a single node with all processing capabilities."""
        if not hasattr(node, 'content_text') or not node.content_text:
            return
        
        # Generate summary
        if not hasattr(node, 'summary') or not node.summary:
            node.summary = self.processor.generate_content_summary(node.content_text)
        
        # Generate keywords
        if not hasattr(node, 'keywords') or not node.keywords:
            node.keywords = self.processor.generate_keyword_list(node.content_text)
        
        # Create content chunks
        if not hasattr(node, 'content_chunks') or not node.content_chunks:
            node.content_chunks = self.processor.create_content_chunks(node.content_text)
        
        # Extract sentences
        if not hasattr(node, 'sentences') or not node.sentences:
            node.sentences = self.processor.extract_sentences_from_content(node.content_text)
        
        # Generate embeddings
        node.header_embedding = self.embedding_generator.generate_header_embedding(node.header)
        node.summary_embedding = self.embedding_generator.generate_summary_embedding(
            getattr(node, 'summary', '')
        )
        
        if hasattr(node, 'content_chunks') and node.content_chunks:
            node.chunk_embeddings = self.embedding_generator.generate_chunk_embeddings(
                node.content_chunks
            )
        
        if hasattr(node, 'sentences') and node.sentences:
            node.sentence_embeddings = self.embedding_generator.generate_sentence_embeddings(
                node.sentences
            )
    
    def search_nodes(self, query: str, content_tree, 
                    top_k: int = 10, 
                    semantic_weight: Optional[float] = None,
                    lexical_weight: Optional[float] = None,
                    parameters: Optional[Any] = None) -> List[Tuple[Any, float]]:
        """
        Search for relevant nodes using both semantic and lexical similarity.
        
        Args:
            query: Search query
            content_tree: ContentTree to search
            top_k: Number of results to return
            semantic_weight: Weight for semantic similarity (optional)
            lexical_weight: Weight for lexical similarity (optional)
            parameters: SearchParameters object (optional)
            
        Returns:
            List of (node, combined_score) tuples
        """
        # Use provided parameters or fall back to instance parameters
        search_params = parameters or self.parameters
        
        # Use provided weights or fall back to parameters, then to defaults
        if semantic_weight is None:
            semantic_weight = search_params.combined_weights.semantic if search_params else 0.6
        if lexical_weight is None:
            lexical_weight = search_params.combined_weights.lexical if search_params else 0.4
        
        print(f"Searching for: '{query}'")
        
        # Generate query embedding
        query_embedding = self.embedding_generator.generate_embeddings([query])[0]
        
        # Get all content nodes
        all_nodes = content_tree.tree_node_iterator()
        content_nodes = [node for node in all_nodes if node.header_level > 0]
        
        # Calculate lexical similarity scores (normalized to 0-1.0 range)
        lexical_scores = self.index_builder.calculate_normalized_lexical_similarity(query, parameters)
        
        # Calculate combined scores
        node_scores = []
        for node in content_nodes:
            semantic_score = 0.0
            lexical_score = lexical_scores.get(node.node_id, 0.0)
            
            # Calculate semantic similarity if embeddings exist
            if hasattr(node, 'header_embedding') and node.header_embedding is not None:
                semantic_score = calculate_semantic_similarity(
                    query_embedding,
                    getattr(node, 'sentence_embeddings', None),
                    node.header_embedding,
                    getattr(node, 'summary_embedding', None),
                    getattr(node, 'chunk_embeddings', None),
                    getattr(node, 'sentence_embeddings', None),
                    search_params.semantic_weights if search_params else None
                )
            
            # Combine scores
            combined_score = (semantic_weight * semantic_score + 
                            lexical_weight * lexical_score)
            
            if combined_score > 0:
                node_scores.append((node, combined_score))
        
        # Sort by score and return top-k
        node_scores.sort(key=lambda x: x[1], reverse=True)
        return node_scores[:top_k]
