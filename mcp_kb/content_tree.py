import re
import os
from typing import List, Optional


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
    
    def add_child(self, child_node: 'ContentNode'):
        """Add a child node and set this node as its parent."""
        child_node.parent_node = self
        self.child_nodes.append(child_node)
    
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
    
    def content_tree_constructor(self, markdown_file_path: str) -> ContentNode:
        """
        Construct a content tree from a single markdown file.
        
        Args:
            markdown_file_path (str): Path to the markdown file
            
        Returns:
            ContentNode: The root node of the constructed tree for this file
        """
        with open(markdown_file_path, 'r', encoding='utf-8') as file:
            markdown_text = file.read()
        
        return self._parse_markdown_to_tree(markdown_text)
    
    def build_textbook_tree(self, md_files_directory: str) -> None:
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
        for filename in md_files:
            file_path = os.path.join(md_files_directory, filename)
            chapter_tree = self.content_tree_constructor(file_path)
            
            # Add the chapter/appendix as a child of the root
            if chapter_tree and chapter_tree.child_nodes:
                # The first child of the chapter_tree is typically the main chapter/appendix node
                main_node = chapter_tree.child_nodes[0] if chapter_tree.child_nodes else chapter_tree
                self.root.add_child(main_node)
    
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
    
    def _parse_markdown_to_tree(self, markdown_text: str) -> ContentNode:
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
            
            if match:
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
    
    def print_tree_structure(self, node: Optional[ContentNode] = None, indent: int = 0):
        """
        Print the tree structure for debugging purposes.
        
        Args:
            node (ContentNode, optional): Node to start from. Uses root if None.
            indent (int): Current indentation level
        """
        if node is None:
            node = self.root
        
        print('  ' * indent + f"[{node.node_id}] Level {node.header_level}: {node.header}")
        for child in node.child_nodes:
            self.print_tree_structure(child, indent + 1)


# Example usage and testing
if __name__ == "__main__":
    # Create a ContentTree instance
    tree = ContentTree()
    
    # Build the textbook tree from markdown files
    md_directory = "/Users/chemxai/GenAI/AI_Tutor/mcp_kb/md_files"
    tree.build_textbook_tree(md_directory)
    
    # Print tree structure
    print("Textbook Structure:")
    tree.print_tree_structure()
    
    # Get all nodes
    all_nodes = tree.tree_node_iterator()
    print(f"\nTotal nodes: {len(all_nodes)}")
    
    # Find a specific chapter
    chapter1 = tree.find_node_by_header("Chapter 1 - Essential Ideas")
    if chapter1:
        print(f"\nFound: {chapter1}")
        print(f"Content preview: {chapter1.content_text[:200]}...")
    
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
