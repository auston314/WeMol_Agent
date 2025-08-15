"""
High-level orchestrator for content enhancement across the ContentTree.
Split out from utils.py to reduce file size and improve modularity.
"""
from typing import List, Tuple, Optional, Any

from .content_processing import ContentProcessor
from .embeddings import EmbeddingGenerator, calculate_semantic_similarity
from .indexing import InverseIndexBuilder


class ContentEnhancer:
    """Main class that coordinates all content enhancement operations."""

    def __init__(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b',
                 llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                 embedding_model: str = "text-embedding-3-large",
                 parameters: Optional[Any] = None):
        self.processor = ContentProcessor(llm_type, llm_model, llm_api_url)
        self.embedding_generator = EmbeddingGenerator(embedding_model)
        self.index_builder = InverseIndexBuilder(parameters=parameters)
        if parameters is None:
            try:
                from .parameters import DEFAULT_PARAMETERS
                self.parameters = DEFAULT_PARAMETERS
            except Exception:
                self.parameters = None
        else:
            self.parameters = parameters

    def enhance_content_tree(self, content_tree) -> None:
        print("Enhancing content tree...")
        all_nodes = content_tree.tree_node_iterator()
        content_nodes = [node for node in all_nodes if node.header_level > 0]
        print(f"Processing {len(content_nodes)} nodes...")
        for i, node in enumerate(content_nodes, 1):
            print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
            self._enhance_single_node(node)
        self.index_builder.build_ngram_indexes(content_nodes)
        print("Content tree enhancement complete!")

    def _enhance_single_node(self, node) -> None:
        if not hasattr(node, 'content_text') or not node.content_text:
            return
        if not getattr(node, 'summary', None):
            node.summary = self.processor.generate_content_summary(node.content_text)
        if not getattr(node, 'keywords', None):
            node.keywords = self.processor.generate_keyword_list(node.content_text)
        if not getattr(node, 'content_chunks', None):
            node.content_chunks = self.processor.create_content_chunks(node.content_text)
        if not getattr(node, 'sentences', None):
            node.sentences = self.processor.extract_sentences_from_content(node.content_text)
        node.header_embedding = self.embedding_generator.generate_header_embedding(node.header)
        node.summary_embedding = self.embedding_generator.generate_summary_embedding(getattr(node, 'summary', ''))
        if getattr(node, 'content_chunks', None):
            node.chunk_embeddings = self.embedding_generator.generate_chunk_embeddings(node.content_chunks)
        if getattr(node, 'sentences', None):
            node.sentence_embeddings = self.embedding_generator.generate_sentence_embeddings(node.sentences)

    def search_nodes(self, query: str, content_tree,
                     top_k: int = 10,
                     semantic_weight: Optional[float] = None,
                     lexical_weight: Optional[float] = None,
                     parameters: Optional[Any] = None) -> List[Tuple[Any, float]]:
        """Search for relevant nodes using both semantic and lexical similarity."""
        search_params = parameters or self.parameters
        if semantic_weight is None:
            semantic_weight = search_params.combined_weights.semantic if search_params else 0.6
        if lexical_weight is None:
            lexical_weight = search_params.combined_weights.lexical if search_params else 0.4
        print(f"Searching for: '{query}'")
        query_embedding = self.embedding_generator.generate_embeddings([query])[0]
        all_nodes = content_tree.tree_node_iterator()
        content_nodes = [node for node in all_nodes if node.header_level > 0]
        lexical_scores = self.index_builder.calculate_normalized_lexical_similarity(query, parameters)
        node_scores = []
        for node in content_nodes:
            semantic_score = 0.0
            lexical_score = lexical_scores.get(node.node_id, 0.0)
            if getattr(node, 'header_embedding', None) is not None:
                semantic_score = calculate_semantic_similarity(
                    query_embedding,
                    getattr(node, 'sentence_embeddings', None),
                    node.header_embedding,
                    getattr(node, 'summary_embedding', None),
                    getattr(node, 'chunk_embeddings', None),
                    getattr(node, 'sentence_embeddings', None),
                    search_params.semantic_weights if search_params else None,
                )
            combined_score = (semantic_weight * semantic_score + lexical_weight * lexical_score)
            if combined_score > 0:
                node_scores.append((node, combined_score))
        node_scores.sort(key=lambda x: x[1], reverse=True)
        return node_scores[:top_k]
