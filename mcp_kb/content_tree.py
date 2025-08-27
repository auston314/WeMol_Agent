import re
import os
from openai import OpenAI
import numpy as np
import pandas as pd
from typing import List, Optional, Any

class ContentNode:
    """
    Represents a single node in the content tree structure.
    Each node corresponds to a markdown header and its associated content.
    """
    
    def __init__(self, header: str, content_text: str = "", header_level: int = 0, 
                 parent_node: Optional['ContentNode'] = None, node_id: int = -1):
        """
        Initialize a ContentNode.
        
        Args:
            header (str): The header text (without the # symbols)
            content_text (str): The content text that follows this header
            header_level (int): The level of the header (number of # symbols)
            parent_node (ContentNode, optional): The parent node
            node_id (int): Unique identifier for this node
        """
        self.header = header
        self.content_text = content_text
        self.header_level = header_level
        self.parent_node = parent_node
        self.child_nodes: List[ContentNode] = []
        self.node_id = node_id
        
        # Enhanced attributes for content processing (initialized when needed)
        self.summary = None
        self.knowledge_list = None
        self.keywords: List[str] = None
        self.content_chunks: List[Any] = None  # ContentChunk objects when utils is available
        self.sentences: List[str] = None
        # Add container for generated study questions
        self.questions: List[str] = None
        
        # Embedding attributes (initialized when generated)
        self.header_embedding: Optional[np.ndarray] = None
        self.summary_embedding: Optional[np.ndarray] = None
        self.chunk_embeddings: Optional[np.ndarray] = None
        self.sentence_embeddings: Optional[np.ndarray] = None
    
    def add_child(self, child_node: 'ContentNode'):
        """Add a child node and set this node as its parent."""
        child_node.parent_node = self
        self.child_nodes.append(child_node)
    
    def generate_summary_and_keywords(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                                     llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                                     max_summary_words: int = 30, max_keywords: int = 10):
        """
        Generate summary and keywords for the node's content_text using ContentProcessor.
        
        Args:
            llm_type (str): LLM provider ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for generation
            llm_api_url (str): API URL for the LLM (Ollama only)
            max_summary_words (int): Maximum words in summary
            max_keywords (int): Maximum number of keywords
        """
        if not self.content_text.strip():
            self.summary = ""
            self.keywords = []
            return
        
        try:
            # Import ContentProcessor here to avoid circular imports
            from content_processing import ContentProcessor
            
            # Create processor instance
            processor = ContentProcessor(llm_type, llm_model, llm_api_url)
            
            # Generate summary
            raw_summary = processor.generate_content_summary(
                self.content_text, max_summary_words
            )
            
            # Clean up summary by removing triple backticks and extra whitespace
            self.summary = raw_summary.strip()
            if self.summary.startswith('```') and self.summary.endswith('```'):
                self.summary = self.summary[3:-3].strip()
            
            # Generate keywords
            raw_keywords = processor.generate_keyword_list(
                self.content_text, max_keywords
            )
            
            # Filter out common non-content words
            filter_words = {'json', 'list', 'format', 'response', 'keywords', 'text', 'following'}
            self.keywords = [kw for kw in raw_keywords if kw.lower() not in filter_words]
            
        except Exception as e:
            print(f"Error generating summary and keywords for node {self.node_id}: {e}")
            self.summary = ""
            self.keywords = []
    
    def create_content_chunks(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                             llm_api_url: str = 'https://chatmol.org/ollama/api/generate'):
        """
        Create content chunks for the node's content_text using ContentProcessor.
        
        Args:
            llm_type (str): LLM provider ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for processing
            llm_api_url (str): API URL for the LLM (Ollama only)
        """
        if not self.content_text.strip():
            self.content_chunks = []
            return
        
        try:
            # Import ContentProcessor here to avoid circular imports
            from content_processing import ContentProcessor
            
            # Create processor instance
            processor = ContentProcessor(llm_type, llm_model, llm_api_url)
            
            # Create content chunks
            self.content_chunks = processor.create_content_chunks(self.content_text)
            
        except Exception as e:
            print(f"Error creating content chunks for node {self.node_id}: {e}")
            self.content_chunks = []
    
    def extract_sentences(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                         llm_api_url: str = 'https://chatmol.org/ollama/api/generate'):
        """
        Extract sentences from the node's content_text using ContentProcessor.
        
        Args:
            llm_type (str): LLM provider ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for processing
            llm_api_url (str): API URL for the LLM (Ollama only)
        """
        if not self.content_text.strip():
            self.sentences = []
            return
        
        try:
            # Import ContentProcessor here to avoid circular imports
            from content_processing import ContentProcessor
            
            # Create processor instance
            processor = ContentProcessor(llm_type, llm_model, llm_api_url)
            
            # Extract sentences
            self.sentences = processor.extract_sentences_from_content(self.content_text)
            
        except Exception as e:
            print(f"Error extracting sentences for node {self.node_id}: {e}")
            self.sentences = []
    
    def generate_questions(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                           llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                           max_questions: int = 50) -> None:
        """
        Generate study questions for this node's content as a JSON list of strings.
        The LLM is instructed to internally identify facts, relationships, and entities,
        and return ONLY a JSON array of questions answerable from the content.
        """
        if not self.content_text.strip():
            self.questions = []
            return
        try:
            from content_processing import ContentProcessor
            if not self.summary:
                self.generate_summary_and_keywords(llm_type, llm_model, llm_api_url)
            summary = self.summary
            processor = ContentProcessor(llm_type, llm_model, llm_api_url)
            if not self.knowledge_list:
                self.knowledge_list = processor.generate_knowledge_list(self.content_text)
            knowledge_graph = self.knowledge_list
            # Estimat max question base on content length
            content_text = self.header + "\n\n" + self.content_text
            max_questions = max(1, len(content_text) // 200)
            #questions = processor.generate_questions_json(self.content_text, max_questions=max_questions)
            questions = processor.generate_questions(self.content_text, summary, knowledge_graph, max_questions)
            # Ensure list of strings and limit to max_questions
            self.questions = [str(q).strip() for q in (questions or []) if str(q).strip()][:max_questions]
        except Exception as e:
            print(f"Error generating questions for node {self.node_id}: {e}")
            self.questions = []

    def process_content(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                       llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                       max_summary_words: int = 30, max_keywords: int = 10,
                       embedding_model: str = "text-embedding-3-large",
                       generate_embeddings: bool = True):
        """
        Process all content for this node: generate summary, keywords, content chunks, sentences, and embeddings.
        
        Args:
            llm_type (str): LLM provider ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for processing
            llm_api_url (str): API URL for the LLM (Ollama only)
            max_summary_words (int): Maximum words in summary
            max_keywords (int): Maximum number of keywords
            embedding_model (str): OpenAI embedding model to use for embeddings
            generate_embeddings (bool): Whether to generate embeddings
        """
        print("Process node content ........")
        # Generate all content processing components
        # Check if summary and keywords already exist to avoid redundant calls
        if not self.summary or not self.keywords:
            self.generate_summary_and_keywords(llm_type, llm_model, llm_api_url, max_summary_words, max_keywords)
        # Check if content chunks exist
        if not self.content_chunks:
            self.create_content_chunks(llm_type, llm_model, llm_api_url)
        # Check if sentences exist
        if not self.sentences:
            self.extract_sentences(llm_type, llm_model, llm_api_url)
        # Check if knowledge list exists
        if not self.knowledge_list:
            from content_processing import ContentProcessor
            processor = ContentProcessor(llm_type, llm_model, llm_api_url)
            self.knowledge_list = processor.generate_knowledge_list(self.content_text)
        # Generate study questions in list format
        if not self.questions:  
            self.generate_questions(llm_type, llm_model, llm_api_url)
        #self.generate_questions(llm_type, llm_model, llm_api_url)

        # Generate embeddings if requested
        if generate_embeddings:
            self.generate_embeddings(embedding_model)
    
    def generate_embeddings(self, embedding_model: str = "text-embedding-3-large"):
        """
        Generate embeddings for header, summary, chunks, and sentences using EmbeddingGenerator.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
        """
        try:
            # Import EmbeddingGenerator here to avoid circular imports
            from embeddings import EmbeddingGenerator
            
            # Create embedding generator instance
            embedding_gen = EmbeddingGenerator(model=embedding_model)
            
            # Generate header embedding
            self.header_embedding = embedding_gen.generate_header_embedding(self.header)
            
            # Generate summary embedding
            self.summary_embedding = embedding_gen.generate_summary_embedding(self.summary)
            
            # Generate chunk embeddings
            if self.content_chunks:
                self.chunk_embeddings = embedding_gen.generate_chunk_embeddings(self.content_chunks)
            
            # Generate sentence embeddings
            if self.sentences:
                self.sentence_embeddings = embedding_gen.generate_sentence_embeddings(self.sentences)
            
            # Generate question embeddings
            if self.questions:
                self.question_embeddings = embedding_gen.generate_sentence_embeddings(self.questions)

        except Exception as e:
            print(f"Error generating embeddings for node {self.node_id}: {e}")
            # Keep existing None values on error
    
    def generate_header_embedding(self, embedding_model: str = "text-embedding-3-large"):
        """
        Generate embedding for the node header only.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
        """
        try:
            from embeddings import EmbeddingGenerator
            embedding_gen = EmbeddingGenerator(model=embedding_model)
            self.header_embedding = embedding_gen.generate_header_embedding(self.header)
        except Exception as e:
            print(f"Error generating header embedding for node {self.node_id}: {e}")
    
    def generate_summary_embedding(self, embedding_model: str = "text-embedding-3-large"):
        """
        Generate embedding for the node summary only.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
        """
        try:
            from embeddings import EmbeddingGenerator
            embedding_gen = EmbeddingGenerator(model=embedding_model)
            self.summary_embedding = embedding_gen.generate_summary_embedding(self.summary)
        except Exception as e:
            print(f"Error generating summary embedding for node {self.node_id}: {e}")
    
    def generate_chunk_embeddings(self, embedding_model: str = "text-embedding-3-large"):
        """
        Generate embeddings for the node content chunks only.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
        """
        try:
            from embeddings import EmbeddingGenerator
            embedding_gen = EmbeddingGenerator(model=embedding_model)
            if self.content_chunks:
                self.chunk_embeddings = embedding_gen.generate_chunk_embeddings(self.content_chunks)
        except Exception as e:
            print(f"Error generating chunk embeddings for node {self.node_id}: {e}")
    
    def generate_sentence_embeddings(self, embedding_model: str = "text-embedding-3-large"):
        """
        Generate embeddings for the node sentences only.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
        """
        try:
            from embeddings import EmbeddingGenerator
            embedding_gen = EmbeddingGenerator(model=embedding_model)
            if self.sentences:
                self.sentence_embeddings = embedding_gen.generate_sentence_embeddings(self.sentences)
        except Exception as e:
            print(f"Error generating sentence embeddings for node {self.node_id}: {e}")
    
    def __repr__(self):
        return f"ContentNode(id={self.node_id}, level={self.header_level}, header='{self.header}', children={len(self.child_nodes)})"


class ContentTree:
    """
    Represents the hierarchical structure of a textbook with chapters and sections.
    """
    
    def __init__(self):
        """Initialize the ContentTree with a root node."""
        self.root = ContentNode(header="Root", header_level=0, node_id=0)
        self._node_counter = 1  # Start from 1 since root is 0
        self.inverse_index = {}  # Initialize inverse index
        self.inverse_index_builder = None  # Initialize inverse index builder
    
    def content_tree_constructor(self, markdown_file_path: str, max_level: int = 3) -> ContentNode:
        """
        Construct a content tree from a single markdown file.
        
        Args:
            markdown_file_path (str): Path to the markdown file
            
        Returns:
            ContentNode: The root node of the constructed tree for this file
        """
        with open(markdown_file_path, 'r', encoding='utf-8') as file:
            markdown_text = file.read()
        
        return self._parse_markdown_to_tree(markdown_text, max_level)
    
    def build_textbook_tree(self, md_files_directory: str, max_level: int = 3) -> None:
        """
        Build the complete textbook tree from all markdown files in the directory.
        
        Args:
            md_files_directory (str): Path to the directory containing markdown files
        """
        # Get all markdown files
        md_files = []
        for filename in os.listdir(md_files_directory):
            if filename.endswith('.md') and filename != 'test':
                md_files.append(filename)
        
        # Sort files to ensure proper order (Preface, Chapter_1, Chapter_2, ..., Appendix_A, ...)
        md_files.sort(key=self._sort_key)
        
        # Process each file
        file_counter = 0
        for filename in md_files:
            file_path = os.path.join(md_files_directory, filename)
            chapter_tree = self.content_tree_constructor(file_path, max_level=max_level)
            # Start Hack
            # file_counter += 1
            # if (file_counter > 2):
            #     break
            # End of Hack
            # Add the chapter/appendix as a child of the root
            if chapter_tree and chapter_tree.child_nodes:
                # The first child of the chapter_tree is typically the main chapter/appendix node
                main_node = chapter_tree.child_nodes[0] if chapter_tree.child_nodes else chapter_tree
                self.root.add_child(main_node)
                # Check multiple children and add them to root if the remaining children nodes have the same level as the main node
                for child in chapter_tree.child_nodes[1:]:
                    if child.header_level == main_node.header_level:
                        self.root.add_child(child)

        # Reassign node IDs sequentially to eliminate gaps
        self.reassign_node_ids()
    
    def reassign_node_ids(self) -> None:
        """
        Reassign node IDs sequentially based on tree traversal order.
        This eliminates gaps caused by temporary File Root nodes.
        Root starts at ID 1, and all other nodes follow sequentially.
        """
        all_nodes = self.tree_node_iterator()
        
        # Reassign IDs starting from 1 for root
        for i, node in enumerate(all_nodes, 1):
            node.node_id = i
    
    def _sort_key(self, filename: str) -> tuple:
        """Sort key function to order files properly."""
        if filename == 'Preface.md':
            return (0, 0)
        elif filename.startswith('Chapter_'):
            chapter_num = int(filename.split('_')[1].split('.')[0])
            return (1, chapter_num)
        elif filename.startswith('Appendix_'):
            appendix_letter = filename.split('_')[1].split('.')[0]
            return (2, ord(appendix_letter))
        else:
            return (3, 0)
    
    def _parse_markdown_to_tree(self, markdown_text: str, max_level: int = 3) -> ContentNode:
        """
        Parse markdown text and create a tree structure.
        
        Args:
            markdown_text (str): The markdown content
            
        Returns:
            ContentNode: Root node of the parsed tree
        """
        lines = markdown_text.split('\n')
        file_root = ContentNode(header="File Root", header_level=0, node_id=self._node_counter)
        self._node_counter += 1
        
        current_node = file_root
        content_block = ''
        node_stack = [file_root]  # Stack to manage parent-child relationships
        
        for line in lines:
            # Check if line is a markdown header
            match = re.match(r'^(#+)\s*(.*)', line)
            level = -1
            if match:
                level = len(match.group(1))  # Number of # symbols
            
            if match and level <= max_level:
                # Process any accumulated content for the current node
                if content_block.strip():
                    current_node.content_text = content_block.strip()
                    content_block = ''
                
                # Extract header information
                level = len(match.group(1))  # Number of # symbols
                header = match.group(2).strip()
                
                # Create new node
                new_node = ContentNode(
                    header=header,
                    header_level=level,
                    node_id=self._node_counter
                )
                self._node_counter += 1
                
                # Find correct parent for the new node
                while node_stack and node_stack[-1].header_level >= level:
                    node_stack.pop()
                
                parent_node = node_stack[-1] if node_stack else file_root
                parent_node.add_child(new_node)
                node_stack.append(new_node)
                current_node = new_node
            else:
                content_block += line + '\n'
        
        # Add any remaining content to the last node
        if content_block.strip():
            current_node.content_text = content_block.strip()
        
        return file_root
    
    def tree_node_iterator(self, start_node: Optional[ContentNode] = None) -> List[ContentNode]:
        """
        Iterate through all nodes in the tree using depth-first search.
        
        Args:
            start_node (ContentNode, optional): Node to start from. Uses root if None.
            
        Returns:
            List[ContentNode]: List of all nodes in depth-first order
        """
        if start_node is None:
            start_node = self.root
        
        nodes = []
        
        def _traverse(node: ContentNode):
            nodes.append(node)
            for child in node.child_nodes:
                _traverse(child)
        
        _traverse(start_node)
        return nodes
    
    def content_retriever(self, node: ContentNode) -> str:
        """
        Retrieve content text of a node and all its child nodes recursively.
        
        Args:
            node (ContentNode): The node to retrieve content from
            
        Returns:
            str: Combined content text from the node and all its descendants
        """
        content = []
        
        def _collect_content(current_node: ContentNode):
            # Add current node's content
            if current_node.content_text.strip():
                # Add header if it's not the root
                if current_node.header_level > 0:
                    header_prefix = '#' * current_node.header_level
                    content.append(f"{header_prefix} {current_node.header}\n")
                content.append(current_node.content_text)
                content.append('\n\n')
            
            # Recursively collect content from children
            for child in current_node.child_nodes:
                _collect_content(child)
        
        _collect_content(node)
        return ''.join(content).strip()
    
    def find_node_by_header(self, header: str, start_node: Optional[ContentNode] = None) -> Optional[ContentNode]:
        """
        Find a node by its header text.
        
        Args:
            header (str): The header text to search for
            start_node (ContentNode, optional): Node to start search from. Uses root if None.
            
        Returns:
            ContentNode or None: The found node or None if not found
        """
        if start_node is None:
            start_node = self.root
        
        all_nodes = self.tree_node_iterator(start_node)
        
        # Exact match first
        for node in all_nodes:
            if node.header == header:
                return node
        
        # Case-insensitive match
        header_lower = header.lower()
        for node in all_nodes:
            if node.header.lower() == header_lower:
                return node
        
        # Partial match
        for node in all_nodes:
            if header in node.header or node.header in header:
                return node
        
        return None
    
    def get_chapter_nodes(self) -> List[ContentNode]:
        """Get all chapter nodes (level 2 nodes that start with 'Chapter')."""
        chapters = []
        for child in self.root.child_nodes:
            if child.header.startswith('Chapter') and child.header_level == 2:
                chapters.append(child)
        return chapters
    
    def get_appendix_nodes(self) -> List[ContentNode]:
        """Get all appendix nodes (level 2 nodes that start with 'Appendix')."""
        appendices = []
        for child in self.root.child_nodes:
            if child.header.startswith('Appendix') and child.header_level == 2:
                appendices.append(child)
        return appendices
    
    def rename_repeating_headers(self) -> None:
        """
        Rename repeating headers by prefixing them with their parent's header.
        This helps differentiate sections like 'Key Terms', 'Summary' that appear 
        in multiple chapters.
        """
        # First, collect all headers and count their occurrences
        header_counts = {}
        all_nodes = self.tree_node_iterator()
        
        for node in all_nodes:
            if node.header_level > 0:  # Skip root node
                header = node.header
                if header in header_counts:
                    header_counts[header] += 1
                else:
                    header_counts[header] = 1
        
        # Find headers that appear more than once
        repeating_headers = {header for header, count in header_counts.items() if count > 1}
        
        # Rename nodes with repeating headers
        for node in all_nodes:
            if (node.header in repeating_headers and 
                node.parent_node and 
                node.parent_node.header != "Root" and
                node.header_level > 0):
                
                # Get the parent's header (clean it up if needed)
                parent_header = node.parent_node.header
                
                # For chapter headers like "Chapter 1 - Essential Ideas", 
                # extract just "Chapter 1" part
                if " - " in parent_header:
                    parent_prefix = parent_header.split(" - ")[0]
                else:
                    parent_prefix = parent_header
                
                # Create new header with parent prefix
                new_header = f"{parent_prefix} {node.header}"
                node.header = new_header
    
    def generate_all_summaries_and_keywords(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                                          llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                                          max_summary_words: int = 30, max_keywords: int = 10,
                                          skip_root: bool = True):
        """
        Generate summaries and keywords for all nodes in the tree.
        
        Args:
            llm_type (str): LLM provider to use ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for generation
            llm_api_url (str): API URL for the LLM (Ollama only)
            max_summary_words (int): Maximum words in summary
            max_keywords (int): Maximum number of keywords
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Generating summaries and keywords for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            if node.content_text.strip():  # Only process nodes with content
                print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
                node.generate_summary_and_keywords(
                    llm_type=llm_type,
                    llm_model=llm_model,
                    llm_api_url=llm_api_url,
                    max_summary_words=max_summary_words,
                    max_keywords=max_keywords
                )
            else:
                print(f"Skipping node {i}/{len(content_nodes)} (no content): {node.header}")
        
        print("Summary and keyword generation complete!")
    
    def process_all_content(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                           llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                           max_summary_words: int = 30, max_keywords: int = 10,
                           embedding_model: str = "text-embedding-3-large",
                           generate_embeddings: bool = True,
                           skip_root: bool = True):
        """
        Process all content for all nodes in the tree: generate summaries, keywords, 
        content chunks, sentences, and embeddings.
        
        Args:
            llm_type (str): LLM provider to use ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for processing
            llm_api_url (str): API URL for the LLM (Ollama only)
            max_summary_words (int): Maximum words in summary
            max_keywords (int): Maximum number of keywords
            embedding_model (str): OpenAI embedding model to use for embeddings
            generate_embeddings (bool): Whether to generate embeddings
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Processing all content for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            if node.content_text.strip():  # Only process nodes with content
                print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
                node.process_content(
                    llm_type=llm_type,
                    llm_model=llm_model,
                    llm_api_url=llm_api_url,
                    max_summary_words=max_summary_words,
                    max_keywords=max_keywords,
                    embedding_model=embedding_model,
                    generate_embeddings=generate_embeddings
                )
            else:
                print(f"Skipping node {i}/{len(content_nodes)} (no content): {node.header}")
        
        print("Complete content processing finished!")
    
    def create_all_content_chunks(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                                 llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                                 skip_root: bool = True):
        """
        Create content chunks for all nodes in the tree.
        
        Args:
            llm_type (str): LLM provider to use ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for processing
            llm_api_url (str): API URL for the LLM (Ollama only)
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Creating content chunks for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            if node.content_text.strip():  # Only process nodes with content
                print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
                node.create_content_chunks(llm_type=llm_model, llm_api_url=llm_api_url)
            else:
                print(f"Skipping node {i}/{len(content_nodes)} (no content): {node.header}")
        
        print("Content chunk creation complete!")
    
    def extract_all_sentences(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                             llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                             skip_root: bool = True):
        """
        Extract sentences for all nodes in the tree.
        
        Args:
            llm_type (str): LLM provider to use ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for processing
            llm_api_url (str): API URL for the LLM (Ollama only)
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Extracting sentences for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            if node.content_text.strip():  # Only process nodes with content
                print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
                node.extract_sentences(llm_type=llm_model, llm_api_url=llm_api_url)
            else:
                print(f"Skipping node {i}/{len(content_nodes)} (no content): {node.header}")
        
        print("Sentence extraction complete!")
    
    def generate_all_embeddings(self, embedding_model: str = "text-embedding-3-large",
                               skip_root: bool = True):
        """
        Generate embeddings for all nodes in the tree.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Generating embeddings for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
            node.generate_embeddings(embedding_model=embedding_model)
        
        print("Embedding generation complete!")
    
    def generate_all_header_embeddings(self, embedding_model: str = "text-embedding-3-large",
                                      skip_root: bool = True):
        """
        Generate header embeddings for all nodes in the tree.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Generating header embeddings for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
            node.generate_header_embedding(embedding_model=embedding_model)
        
        print("Header embedding generation complete!")
    
    def generate_all_summary_embeddings(self, embedding_model: str = "text-embedding-3-large",
                                       skip_root: bool = True):
        """
        Generate summary embeddings for all nodes in the tree.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Generating summary embeddings for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            if node.summary and node.summary.strip():  # Only process nodes with summaries
                print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
                node.generate_summary_embedding(embedding_model=embedding_model)
            else:
                print(f"Skipping node {i}/{len(content_nodes)} (no summary): {node.header}")
        
        print("Summary embedding generation complete!")
    
    def generate_all_chunk_embeddings(self, embedding_model: str = "text-embedding-3-large",
                                     skip_root: bool = True):
        """
        Generate chunk embeddings for all nodes in the tree.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Generating chunk embeddings for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            if node.content_chunks:  # Only process nodes with chunks
                print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
                node.generate_chunk_embeddings(embedding_model=embedding_model)
            else:
                print(f"Skipping node {i}/{len(content_nodes)} (no chunks): {node.header}")
        
        print("Chunk embedding generation complete!")
    
    def generate_all_sentence_embeddings(self, embedding_model: str = "text-embedding-3-large",
                                        skip_root: bool = True):
        """
        Generate embeddings for all nodes in the tree.
        
        Args:
            embedding_model (str): OpenAI embedding model to use
            skip_root (bool): Whether to skip the root node
        """
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        print(f"Generating sentence embeddings for {len(content_nodes)} nodes...")
        
        for i, node in enumerate(content_nodes, 1):
            if node.sentences:  # Only process nodes with sentences
                print(f"Processing node {i}/{len(content_nodes)}: {node.header}")
                node.generate_sentence_embeddings(embedding_model=embedding_model)
            else:
                print(f"Skipping node {i}/{len(content_nodes)} (no sentences): {node.header}")
        
        print("Sentence embedding generation complete!")
    
    def process_tree_content(self, llm_type: str = 'ollama', llm_model: str = 'qwen2.5vl:32b', 
                           llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                           max_summary_words: int = 30, max_keywords: int = 10,
                           embedding_model: str = "text-embedding-3-large",
                           generate_embeddings: bool = True,
                           skip_root: bool = True,
                           create_inverse_index: bool = True):
        """
        Process all content for all nodes in the tree and create an inverse index.
        This is a comprehensive function that handles all content processing steps.
        
        Args:
            llm_type (str): LLM provider to use ('ollama', 'openai', 'zai')
            llm_model (str): LLM model to use for processing
            llm_api_url (str): API URL for the LLM (Ollama only)
            max_summary_words (int): Maximum words in summary
            max_keywords (int): Maximum number of keywords
            embedding_model (str): OpenAI embedding model to use for embeddings
            generate_embeddings (bool): Whether to generate embeddings
            skip_root (bool): Whether to skip the root node
            create_inverse_index (bool): Whether to create an inverse index
        """
        print("="*80)
        print("COMPREHENSIVE CONTENT TREE PROCESSING")
        print("="*80)
        
        # Get all nodes to process
        all_nodes = self.tree_node_iterator()
        
        # Filter out root node if requested
        if skip_root:
            content_nodes = [node for node in all_nodes if node.header_level > 0]
        else:
            content_nodes = all_nodes
        
        # Filter to only nodes with content
        content_nodes = [node for node in content_nodes if node.content_text.strip()]
        
        print(f"Processing {len(content_nodes)} content nodes...")
        print(f"LLM Provider: {llm_type}")
        print(f"LLM Model: {llm_model}")
        print(f"Embedding Model: {embedding_model}")
        print(f"Generate Embeddings: {generate_embeddings}")
        print(f"Create Inverse Index: {create_inverse_index}")
        print("-" * 80)
        
        # Process each node
        for i, node in enumerate(content_nodes, 1):
            print(f"\n[{i}/{len(content_nodes)}] Processing node {node.node_id}: {node.header}")
            print(f"Content length: {len(node.content_text)} characters")
            
            try:
                # Process all content for this node
                node.process_content(
                    llm_type=llm_type,
                    llm_model=llm_model,
                    llm_api_url=llm_api_url,
                    max_summary_words=max_summary_words,
                    max_keywords=max_keywords,
                    embedding_model=embedding_model,
                    generate_embeddings=generate_embeddings
                )
                
                # Print processing results
                print(f"  ✓ Summary: {len(node.summary)} chars")
                print(f"  ✓ Keywords: {len(node.keywords)} items")
                print(f"  ✓ Chunks: {len(node.content_chunks)} items")
                print(f"  ✓ Sentences: {len(node.sentences)} items")
                print(f"  ✓ Questions: {len(node.questions)} items")

                if generate_embeddings:
                    embeddings_status = []
                    if node.header_embedding is not None:
                        embeddings_status.append("Header")
                    if node.summary_embedding is not None:
                        embeddings_status.append("Summary")
                    if node.chunk_embeddings is not None:
                        embeddings_status.append("Chunks")
                    if node.sentence_embeddings is not None:
                        embeddings_status.append("Sentences")
                    print(f"  ✓ Embeddings: {', '.join(embeddings_status)}")
                
            except Exception as e:
                print(f"  ❌ Error processing node {node.node_id}: {e}")
        
        print("\n" + "="*80)
        print("CONTENT PROCESSING COMPLETE")
        print("="*80)
        
        # Create inverse index if requested
        if create_inverse_index:
            print("\nCreating inverse index using InverseIndexBuilder...")
            
            try:
                # Import InverseIndexBuilder from new module
                from indexing import InverseIndexBuilder
                
                # Create inverse index builder instance
                self.inverse_index_builder = InverseIndexBuilder(include_stopwords=False)
                
                # Build n-gram indexes for all content nodes
                self.inverse_index_builder.build_ngram_indexes(content_nodes)
                
                print(f"✓ N-gram inverse indexes created successfully!")
                print(f"    - Monograms: {len(self.inverse_index_builder.monogram_index)} terms")
                print(f"    - Bigrams: {len(self.inverse_index_builder.bigram_index)} terms")  
                print(f"    - Trigrams: {len(self.inverse_index_builder.trigram_index)} terms")
                
                # Also store the legacy simple inverse index for backward compatibility
                self.inverse_index = dict(self.inverse_index_builder.monogram_index)
                
                # Print some statistics about the monogram index
                total_terms = sum(len(node_list) for node_list in self.inverse_index.values())
                avg_nodes_per_term = total_terms / len(self.inverse_index) if self.inverse_index else 0
                print(f"✓ Average nodes per term: {avg_nodes_per_term:.2f}")
                
                # Show most common terms from monogram index
                most_common_terms = sorted(self.inverse_index.items(), 
                                         key=lambda x: len(x[1]), reverse=True)[:10]
                print(f"✓ Most common monogram terms:")
                for term, nodes in most_common_terms:
                    print(f"    '{term}': {len(nodes)} nodes")
                
            except Exception as e:
                print(f"❌ Error creating advanced inverse index: {e}")
                print("Falling back to simple inverse index...")
                self.inverse_index = self._create_simple_inverse_index(content_nodes)
                print(f"✓ Simple inverse index created with {len(self.inverse_index)} unique terms")
        
        print("\n" + "="*80)
        print("TREE CONTENT PROCESSING FINISHED!")
        print("="*80)
    
    def _create_simple_inverse_index(self, nodes: List[ContentNode]) -> dict:
        """
        Create a simple inverse index mapping terms to nodes that contain them.
        This is a fallback method when InverseIndexBuilder is not available.
        
        Args:
            nodes (List[ContentNode]): List of nodes to index
            
        Returns:
            dict: Dictionary mapping terms to lists of node IDs
        """
        inverse_index = {}
        
        def add_terms_to_index(terms: List[str], node_id: int):
            """Helper function to add terms to the inverse index."""
            for term in terms:
                if term and len(term.strip()) > 2:  # Skip very short terms
                    term_clean = term.strip().lower()
                    if term_clean not in inverse_index:
                        inverse_index[term_clean] = []
                    if node_id not in inverse_index[term_clean]:
                        inverse_index[term_clean].append(node_id)
        
        for node in nodes:
            node_id = node.node_id
            
            # Index header words
            if node.header:
                header_words = re.findall(r'\b\w+\b', node.header.lower())
                add_terms_to_index(header_words, node_id)
            
            # Index keywords
            if node.keywords:
                add_terms_to_index(node.keywords, node_id)
            
            # Index summary words
            if node.summary:
                summary_words = re.findall(r'\b\w+\b', node.summary.lower())
                add_terms_to_index(summary_words, node_id)
            
            # Index chunk content words (if available)
            if node.content_chunks:
                for chunk in node.content_chunks:
                    if hasattr(chunk, 'text'):
                        chunk_words = re.findall(r'\b\w+\b', chunk.text.lower())
                        add_terms_to_index(chunk_words, node_id)
                    elif isinstance(chunk, str):
                        chunk_words = re.findall(r'\b\w+\b', chunk.lower())
                        add_terms_to_index(chunk_words, node_id)
            
            # Index sentence words
            if node.sentences:
                for sentence in node.sentences:
                    sentence_words = re.findall(r'\b\w+\b', sentence.lower())
                    add_terms_to_index(sentence_words, node_id)
        
        return inverse_index
    
    def search_content(self, query: str, max_results: int = 10, use_ngrams: bool = True) -> List[tuple]:
        """
        Search the content tree for nodes containing query terms.
        
        This is the main search method that uses InverseIndexBuilder with n-gram support
        for advanced lexical similarity scoring.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            use_ngrams (bool): Whether to use n-gram similarity scoring (recommended)
            
        Returns:
            List[tuple]: List of (node_id, score) tuples sorted by relevance
        """
        # Check if advanced inverse index is available
        if hasattr(self, 'inverse_index_builder') and self.inverse_index_builder is not None:
            try:
                if use_ngrams:
                    # Use advanced n-gram search with lexical similarity scoring
                    return self.inverse_index_builder.get_matching_nodes(query, max_results)
                else:
                    # Use simple matching from monogram index
                    results = []
                    query_terms = query.lower().split()
                    node_scores = {}
                    
                    for term in query_terms:
                        if term in self.inverse_index_builder.monogram_index:
                            for node_id in self.inverse_index_builder.monogram_index[term]:
                                node_scores[node_id] = node_scores.get(node_id, 0) + 1
                    
                    # Sort by score and return top results
                    sorted_results = sorted(node_scores.items(), key=lambda x: x[1], reverse=True)
                    return sorted_results[:max_results]
                    
            except Exception as e:
                print(f"Error using InverseIndexBuilder: {e}")
                print("Falling back to simple search...")
        
        # Fallback to simple inverse index search
        if hasattr(self, 'inverse_index') and self.inverse_index:
            return self._simple_search(query, max_results)
        
        print("No search index available. Run process_tree_content() first.")
        return []
    
    def _simple_search(self, query: str, max_results: int) -> List[tuple]:
        """
        Simple search using the basic inverse index as fallback.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            List[tuple]: List of (node_id, score) tuples sorted by relevance
        """
        # Tokenize query
        query_terms = re.findall(r'\b\w+\b', query.lower())
        if not query_terms:
            return []
        
        # Score nodes based on term matches
        node_scores = {}
        
        for term in query_terms:
            if term in self.inverse_index:
                for node_id in self.inverse_index[term]:
                    if node_id not in node_scores:
                        node_scores[node_id] = 0
                    node_scores[node_id] += 1
        
        # Sort by score and return top results
        sorted_results = sorted(node_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:max_results]
    
    def enhanced_search(self, query: str, max_results: int = 10, 
                       semantic_weight: Optional[float] = None, 
                       lexical_weight: Optional[float] = None,
                       parameters: Optional[Any] = None) -> List[tuple]:
        """
        Enhanced search combining lexical similarity with semantic similarity.
        
        Uses both lexical similarity from InverseIndexBuilder and semantic similarity
        from embeddings when available.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            semantic_weight (float, optional): Weight for semantic similarity 
            lexical_weight (float, optional): Weight for lexical similarity
            parameters: SearchParameters object from parameters.py (optional)
            
        Returns:
            List[tuple]: List of (node_id, score) tuples sorted by relevance
        """
        # Get weights from parameters if not provided
        if parameters is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                parameters = DEFAULT_PARAMETERS
            except ImportError:
                # Fallback if parameters.py is not available
                pass
        
        # Use provided weights or fall back to parameters, then to defaults
        if semantic_weight is None:
            semantic_weight = parameters.combined_weights.semantic if parameters else 0.6
        if lexical_weight is None:
            lexical_weight = parameters.combined_weights.lexical if parameters else 0.4
        if not hasattr(self, 'inverse_index_builder') or not self.inverse_index_builder:
            print("Advanced search not available. Using basic search...")
            return self.search_content(query, max_results, use_ngrams=False)
        
        try:
            # Get normalized lexical similarity scores using n-gram analysis (0-1.0 range)
            lexical_scores = self.inverse_index_builder.calculate_normalized_lexical_similarity(query, parameters)
            
            # Generate query embedding for semantic similarity
            semantic_scores = {}
            try:
                from embeddings import EmbeddingGenerator, calculate_semantic_similarity
                embedding_gen = EmbeddingGenerator()
                query_embedding = embedding_gen.generate_embeddings([query])[0]
                
                # Get all content nodes
                all_nodes = self.tree_node_iterator()
                content_nodes = [node for node in all_nodes if node.header_level > 0]
                
                # Calculate semantic similarity for each node that has embeddings
                for node in content_nodes:
                    if (hasattr(node, 'header_embedding') and node.header_embedding is not None):
                        semantic_score = calculate_semantic_similarity(
                            query_embedding,
                            getattr(node, 'sentence_embeddings', None),
                            node.header_embedding,
                            getattr(node, 'summary_embedding', None),
                            getattr(node, 'chunk_embeddings', None),
                            getattr(node, 'sentence_embeddings', None),
                            parameters.semantic_weights if parameters else None
                        )
                        semantic_scores[node.node_id] = semantic_score
                        
            except Exception as e:
                print(f"Warning: Could not calculate semantic similarity: {e}")
                semantic_scores = {}
            
            # Combine lexical and semantic scores
            combined_scores = {}
            
            # Get all relevant node IDs from both scoring methods
            all_node_ids = set(lexical_scores.keys()) | set(semantic_scores.keys())
            
            for node_id in all_node_ids:
                lexical_score = lexical_scores.get(node_id, 0.0)
                semantic_score = semantic_scores.get(node_id, 0.0)
                
                # Calculate combined score
                combined_score = (lexical_weight * lexical_score + 
                                semantic_weight * semantic_score)
                
                if combined_score > 0:
                    combined_scores[node_id] = combined_score
            
            # Convert to list of tuples and sort by score
            results = list(combined_scores.items())
            results.sort(key=lambda x: x[1], reverse=True)
            
            return results[:max_results]
            
        except Exception as e:
            print(f"Error in enhanced search: {e}")
            return self.search_content(query, max_results, use_ngrams=False)
    
    def search_inverse_index(self, query: str, max_results: int = 10) -> List[tuple]:
        """
        DEPRECATED: Use search_content() instead.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            List[tuple]: List of (node_id, score) tuples sorted by relevance
        """
        print("Warning: search_inverse_index() is deprecated. Use search_content() instead.")
        return self.search_content(query, max_results, use_ngrams=False)
    
    def search_content_tree(self, query: str, max_results: int = 10, use_ngrams: bool = True) -> List[ContentNode]:
        """
        Search the content tree and return matching nodes.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            use_ngrams (bool): Whether to use n-gram search with advanced scoring
            
        Returns:
            List[ContentNode]: List of matching content nodes sorted by relevance
        """
        # Use the unified search_content method
        search_results = self.search_content(query, max_results, use_ngrams)
        
        # Convert node IDs to actual nodes
        matching_nodes = []
        all_nodes = self.tree_node_iterator()
        node_map = {node.node_id: node for node in all_nodes}
        
        for node_id, score in search_results:
            if node_id in node_map:
                matching_nodes.append(node_map[node_id])
        
        return matching_nodes
    
    def rag_query(self, user_query: str, top_k: int = 1, 
                  llm_type: str = 'ollama',
                  llm_model: str = 'qwen2.5vl:32b',
                  llm_api_url: str = 'https://chatmol.org/ollama/api/generate',
                  semantic_weight: Optional[float] = None, 
                  lexical_weight: Optional[float] = None,
                  custom_params: Optional[Any] = None,
                  debug: bool = False) -> str:
        """
        Retrieval-Augmented Generation (RAG) function that answers user queries using content from the tree.
        
        This function:
        1. Uses enhanced_search to find relevant content nodes
        2. Retrieves content from top-k most relevant nodes
        3. Generates an answer using the LLM based on the retrieved content
        4. Returns "No information in the provided content for your query" if no relevant content is found
        
        Args:
            user_query (str): The user's question
            top_k (int): Number of top relevant nodes to use for context (default: 1)
            llm_model (str): LLM model to use for answer generation
            llm_api_url (str): API URL for the LLM
            semantic_weight (float, optional): Weight for semantic similarity in enhanced search (deprecated, use custom_params)
            lexical_weight (float, optional): Weight for lexical similarity in enhanced search (deprecated, use custom_params)
            custom_params: Parameters object from parameters.py containing all weight configurations
            debug (bool): Whether to print debug information about retrieved content
            
        Returns:
            str: Generated answer or "No information in the provided content for your query"
        """
        if not user_query.strip():
            return "Please provide a valid query."
        
        # Handle parameter precedence: custom_params > individual weights > defaults
        parameters = custom_params
        if parameters is None:
            try:
                from parameters import DEFAULT_PARAMETERS
                parameters = DEFAULT_PARAMETERS
            except ImportError:
                # Fallback if parameters.py is not available
                parameters = None
        
        # Determine search weights (semantic/lexical combination)
        if semantic_weight is None:
            final_semantic_weight = parameters.combined_weights.semantic if parameters else 0.6
        else:
            final_semantic_weight = semantic_weight
            
        if lexical_weight is None:
            final_lexical_weight = parameters.combined_weights.lexical if parameters else 0.4
        else:
            final_lexical_weight = lexical_weight
        
        try:
            # Step 1: Search for relevant content nodes using enhanced search
            search_results = self.enhanced_search(
                query=user_query, 
                max_results=max(top_k, 5),  # Get a few more to ensure we have options
                semantic_weight=final_semantic_weight,
                lexical_weight=final_lexical_weight,
                parameters=parameters  # Pass full parameters to enhanced_search for semantic similarity weights
            )
            
            if debug:
                print(f"\n🔍 DEBUG: Search results for '{user_query}':")
                print(f"Total search results: {len(search_results)}")
                all_nodes = self.tree_node_iterator()
                node_map = {node.node_id: node for node in all_nodes}
                for i, (node_id, score) in enumerate(search_results[:10], 1):
                    if node_id in node_map:
                        node = node_map[node_id]
                        print(f"  {i}. [Node {node_id}] Score: {score:.4f} | Header: '{node.header}'")
                        print(f"     Content preview: {node.content_text[:100]}...")
                    else:
                        print(f"  {i}. [Node {node_id}] Score: {score:.4f} | NODE NOT FOUND")
                print()
            
            if not search_results:
                if debug:
                    print("❌ DEBUG: No search results found!")
                return "No information in the provided content for your query."
            
            # Step 2: Filter out results with very low relevance scores
            # Only keep results with score > 0.01 to ensure some relevance
            relevant_results = [(node_id, score) for node_id, score in search_results if score > 0.01]
            
            if debug:
                print(f"🔍 DEBUG: Filtering results with score > 0.01:")
                print(f"Results after filtering: {len(relevant_results)}")
                if relevant_results:
                    for i, (node_id, score) in enumerate(relevant_results[:5], 1):
                        if node_id in node_map:
                            node = node_map[node_id]
                            print(f"  {i}. [Node {node_id}] Score: {score:.4f} | Header: '{node.header}'")
                print()
            
            if not relevant_results:
                if debug:
                    print("❌ DEBUG: No relevant results after filtering!")
                return "No information in the provided content for your query."
            
            # Step 3: Get the actual nodes and collect their content
            all_nodes = self.tree_node_iterator()
            node_map = {node.node_id: node for node in all_nodes}
            
            context_parts = []
            source_info = []
            
            if debug:
                print(f"🔍 DEBUG: Collecting content from top-{top_k} results:")
            
            # Take only top_k results
            for i, (node_id, score) in enumerate(relevant_results[:top_k]):
                if node_id in node_map:
                    node = node_map[node_id]
                    
                    if debug:
                        print(f"  Using Node {node_id}: '{node.header}' (score: {score:.4f})")
                        print(f"    Content length: {len(node.content_text)} chars")
                        print(f"    Summary length: {len(node.summary) if node.summary else 0} chars")
                    
                    # Collect comprehensive content from the node
                    content_pieces = []
                    
                    # Add header for context
                    if node.header and node.header != "Root":
                        content_pieces.append(f"Section: {node.header}")
                    
                    # Add main content
                    if node.content_text.strip():
                        content_pieces.append(node.content_text.strip())
                    
                    # Add summary if available and different from content
                    if node.summary and node.summary.strip() and len(node.summary) > 20:
                        if node.summary not in node.content_text:
                            content_pieces.append(f"Summary: {node.summary}")
                    
                    # Combine content pieces
                    if content_pieces:
                        node_content = "\n\n".join(content_pieces)
                        context_parts.append(node_content)
                        source_info.append(f"Node {node_id}: {node.header} (relevance: {score:.3f})")
                        
                        if debug:
                            print(f"    Added content pieces: {len(content_pieces)}")
                            print(f"    Total content for this node: {len(node_content)} chars")
                    else:
                        if debug:
                            print(f"    ❌ No usable content found in this node")
            
            if debug:
                print(f"🔍 DEBUG: Total context parts collected: {len(context_parts)}")
                print()
            
            if not context_parts:
                if debug:
                    print("❌ DEBUG: No context parts collected from any node!")
                return "No information in the provided content for your query."
            
            # Step 4: Create context for the LLM
            context = "\n\n" + "="*50 + "\n\n".join(context_parts)
            
            # Step 5: Generate answer using ContentProcessor
            from content_processing import ContentProcessor
            processor = ContentProcessor(llm_type, llm_model, llm_api_url)
            
            # Create a comprehensive prompt for answering the query
            answer_prompt = (
                f"Based on the provided content below, please answer the following question: "
                f'"{user_query}"\n\n'
                f"Instructions:\n"
                f"1. Use only the information provided in the content below\n"
                f"2. If the content does not contain sufficient information to answer the question, "
                f"respond with: 'No information in the provided content for your query.'\n"
                f"3. Be accurate and cite specific information from the content when possible\n"
                f"4. Keep your answer clear and concise\n"
                f"5. Do not make up information not present in the content\n"
                f"6. If the answer contains a figure caption, make sure to include the picture link, which is usually above the figure caption line.\n\n"
            )

            # Use the flexible LLM service call method
            full_prompt = answer_prompt + context + "\n\n" + f"Based on the provided content above, please answer the following question: {user_query}"
            if debug:
                print(f"🔍 DEBUG: Generated full prompt for LLM:\n{full_prompt[:500]}...")
                print(full_prompt)
            system_message = (
                "You are a helpful assistant. Use ONLY the provided content to answer. "
                "If there isn't enough information, respond exactly with: 'No information in the provided content for your query.'"
            )
            answer = processor._call_llm_unified(full_prompt, system_message=system_message, temperature=0.2, max_tokens=512)
            
            # Clean up the answer
            answer = answer.strip()
            
            # Check if the LLM indicates no information available
            no_info_indicators = [
                "no information in the provided content",
                "not enough information",
                "cannot be answered based on the provided content",
                "insufficient information",
                "the content does not contain"
            ]
            
            if any(indicator in answer.lower() for indicator in no_info_indicators):
                return "No information in the provided content for your query."
            
            # If answer is too short or generic, it might not be useful
            if len(answer) < 20:
                return "No information in the provided content for your query."
            
            return answer
            
        except Exception as e:
            print(f"Error in RAG query processing: {e}")
            return "No information in the provided content for your query."
    
    def print_tree_structure(self, node: Optional[ContentNode] = None, indent: int = 0, 
                           show_summary: bool = False, show_keywords: bool = False,
                           show_chunks: bool = False, show_sentences: bool = False,
                           show_embeddings: bool = False):
        """
        Print the tree structure for debugging purposes.
        
        Args:
            node (ContentNode, optional): Node to start from. Uses root if None.
            indent (int): Current indentation level
            show_summary (bool): Whether to show node summaries
            show_keywords (bool): Whether to show node keywords
            show_chunks (bool): Whether to show content chunks count
            show_sentences (bool): Whether to show sentences count
            show_embeddings (bool): Whether to show embedding status
        """
        if node is None:
            node = self.root
        
        content_length = len(node.content_text)
        summary_info = f" | Summary: {node.summary[:50]}..." if show_summary and node.summary else ""
        keywords_info = f" | Keywords: {', '.join(node.keywords[:5])}" if show_keywords and node.keywords else ""
        chunks_info = f" | Chunks: {len(node.content_chunks)}" if show_chunks and node.content_chunks else ""
        sentences_info = f" | Sentences: {len(node.sentences)}" if show_sentences and node.sentences else ""
        
        # Show embedding status
        embeddings_info = ""
        if show_embeddings:
            embedding_status = []
            if node.header_embedding is not None:
                embedding_status.append("H")
            if node.summary_embedding is not None:
                embedding_status.append("S")  
            if node.chunk_embeddings is not None:
                embedding_status.append("C")
            if node.sentence_embeddings is not None:
                embedding_status.append("T")
            embeddings_info = f" | Embeddings: {'/'.join(embedding_status) if embedding_status else 'None'}"
        
        print('  ' * indent + f"[{node.node_id}] Level {node.header_level}: {node.header} " +
              f"(content: {content_length} chars{summary_info}{keywords_info}{chunks_info}{sentences_info}{embeddings_info})")
        
        for child in node.child_nodes:
            self.print_tree_structure(child, indent + 1, show_summary, show_keywords, show_chunks, show_sentences, show_embeddings)


# Example usage and testing
if __name__ == "__main__":
    # Create a ContentTree instance
    tree = ContentTree()
    
    # Build the textbook tree from markdown files
    md_directory = "/Users/chemxai/GenAI/AI_Tutor/mcp_kb/md_files"
    tree.build_textbook_tree(md_directory)
    
    # Rename repeating headers to make them unique
    tree.rename_repeating_headers()
    
    # Print tree structure
    print("Textbook Structure:")
    tree.print_tree_structure()
    
    # Generate summaries and keywords for all nodes
    print("\n" + "="*60)
    print("GENERATING SUMMARIES AND KEYWORDS")
    print("="*60)
    tree.generate_all_summaries_and_keywords()
    
    # Print tree structure with summaries and keywords
    print("\n" + "="*60)
    print("TREE STRUCTURE WITH SUMMARIES AND KEYWORDS")
    print("="*60)
    tree.print_tree_structure(show_summary=True, show_keywords=True)
    
    # Get all nodes
    all_nodes = tree.tree_node_iterator()
    print(f"\nTotal nodes: {len(all_nodes)}")
    
    # Find a specific chapter and show its enhanced information
    chapter1 = tree.find_node_by_header("Chapter 1 - Essential Ideas")
    if chapter1:
        print(f"\nFound: {chapter1}")
        print(f"Content preview: {chapter1.content_text[:200]}...")
        print(f"Summary: {chapter1.summary}")
        print(f"Keywords: {', '.join(chapter1.keywords)}")
    
    # Get content from a node and its children
    if chapter1:
        section_content = tree.content_retriever(chapter1)
        print(f"\nChapter 1 total content length: {len(section_content)} characters")
    
    # Test: Print headers of all child nodes to verify order
    print("\n" + "="*60)
    print("ORDER VERIFICATION: All Root Child Nodes")
    print("="*60)
    print(f"Total root children: {len(tree.root.child_nodes)}")
    print("\nOrder of all child nodes:")
    for i, child in enumerate(tree.root.child_nodes, 1):
        print(f"{i:2d}. [{child.node_id:4d}] Level {child.header_level}: {child.header}")
    
    # Verify expected order
    expected_order = ["Preface"] + [f"Chapter {i} -" for i in range(1, 22)] + [f"Appendix {chr(65+i)}" for i in range(13)]
    print(f"\nExpected count: Preface(1) + Chapters(21) + Appendices(13) = 35 total")
    print(f"Actual count: {len(tree.root.child_nodes)}")
    
    # Check if order matches expected pattern
    order_correct = True
    for i, child in enumerate(tree.root.child_nodes):
        if i == 0 and not child.header.startswith("Preface"):
            order_correct = False
            print(f"❌ Position {i+1}: Expected Preface, got '{child.header}'")
        elif 1 <= i <= 21 and not child.header.startswith(f"Chapter {i}"):
            order_correct = False
            print(f"❌ Position {i+1}: Expected Chapter {i}, got '{child.header}'")
        elif i > 21 and not child.header.startswith(f"Appendix {chr(65+i-22)}"):
            order_correct = False
            print(f"❌ Position {i+1}: Expected Appendix {chr(65+i-22)}, got '{child.header}'")
    
    if order_correct:
        print("✅ Order verification: All nodes are in correct order!")
    else:
        print("❌ Order verification: Some nodes are out of order.")
    
    # Show some examples of generated summaries and keywords
    print("\n" + "="*60)
    print("EXAMPLES OF GENERATED SUMMARIES AND KEYWORDS")
    print("="*60)
    content_nodes = [node for node in all_nodes if node.header_level > 0 and node.content_text.strip()]
    for i, node in enumerate(content_nodes[:5]):  # Show first 5 content nodes
        print(f"\nNode {i+1}: {node.header}")
        print(f"Content length: {len(node.content_text)} characters")
        print(f"Summary: {node.summary}")
        print(f"Keywords: {', '.join(node.keywords)}")
        print("-" * 40)
