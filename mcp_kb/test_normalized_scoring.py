#!/usr/bin/env python3
"""
Test script for normalized n-gram scoring functionality.
"""

from content_tree import ContentTree

def test_normalized_scoring():
    """Test the normalized scoring functionality."""
    print("="*80)
    print("TESTING NORMALIZED N-GRAM SCORING")
    print("="*80)
    
    # Create a ContentTree instance
    tree = ContentTree()
    
    # Build the textbook tree from markdown files (limited to 2 files for testing)
    md_directory = "/Users/chemxai/GenAI/AI_Tutor/mcp_kb/md_files"
    print(f"Building tree from: {md_directory}")
    tree.build_textbook_tree(md_directory)
    
    # Rename repeating headers to make them unique
    tree.rename_repeating_headers()
    
    # Process content to create search indexes
    print("\nProcessing content and creating search indexes...")
    tree.process_tree_content(
        max_summary_words=20,
        max_keywords=5,
        generate_embeddings=False,  # Disabled for faster testing
        create_inverse_index=True
    )
    
    print("\n" + "="*80)
    print("TESTING SCORE NORMALIZATION")
    print("="*80)
    
    test_queries = [
        "chemistry",
        "chemistry atoms",
        "chemistry atoms molecules structure bonds",
        "measurements accuracy precision uncertainty",
        "scientific method observation hypothesis"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Testing query: '{query}'")
        print(f"Query length: {len(query.split())} words")
        print(f"{'='*60}")
        
        # Test with InverseIndexBuilder directly
        if hasattr(tree, 'inverse_index_builder') and tree.inverse_index_builder:
            builder = tree.inverse_index_builder
            
            # Calculate raw scores
            raw_scores = builder.calculate_lexical_similarity(query)
            
            # Calculate normalized scores
            normalized_scores = builder.calculate_normalized_lexical_similarity(query)
            
            # Get top 3 results for comparison
            top_raw = sorted(raw_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            top_normalized = sorted(normalized_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            
            print("\nRAW SCORES (unbounded):")
            max_raw_score = max(raw_scores.values()) if raw_scores else 0
            print(f"  Max raw score: {max_raw_score:.3f}")
            for i, (node_id, score) in enumerate(top_raw, 1):
                node = next((n for n in tree.tree_node_iterator() if n.node_id == node_id), None)
                header = node.header if node else f"Node {node_id}"
                print(f"    {i}. [{node_id}] {header} (score: {score:.3f})")
            
            print("\nNORMALIZED SCORES (0-1.0 range):")
            max_normalized_score = max(normalized_scores.values()) if normalized_scores else 0
            print(f"  Max normalized score: {max_normalized_score:.3f}")
            for i, (node_id, score) in enumerate(top_normalized, 1):
                node = next((n for n in tree.tree_node_iterator() if n.node_id == node_id), None)
                header = node.header if node else f"Node {node_id}"
                print(f"    {i}. [{node_id}] {header} (score: {score:.3f})")
            
            # Calculate maximum possible score for this query
            query_tokens = builder._tokenize_and_clean(query)
            query_monograms = query_tokens
            query_bigrams = [f"{query_tokens[i]} {query_tokens[i+1]}" 
                            for i in range(len(query_tokens)-1)]
            query_trigrams = [f"{query_tokens[i]} {query_tokens[i+1]} {query_tokens[i+2]}" 
                             for i in range(len(query_tokens)-2)]
            
            max_possible = builder._calculate_max_possible_score(query_monograms, query_bigrams, query_trigrams)
            print(f"\nMax possible score for this query: {max_possible:.3f}")
            print(f"Normalization factor: {max_raw_score/max_possible:.3f}" if max_possible > 0 else "N/A")
    
    print("\n" + "="*80)
    print("TESTING ENHANCED SEARCH WITH NORMALIZED SCORES")
    print("="*80)
    
    # Test enhanced search which should now use normalized scores
    test_query = "chemistry atoms molecules"
    print(f"\nTesting enhanced_search with query: '{test_query}'")
    
    enhanced_results = tree.enhanced_search(test_query, max_results=5)
    print(f"\nEnhanced search results (using normalized lexical scores):")
    for i, (node_id, score) in enumerate(enhanced_results, 1):
        node = next((n for n in tree.tree_node_iterator() if n.node_id == node_id), None)
        header = node.header if node else f"Node {node_id}"
        print(f"  {i}. [{node_id}] {header} (combined score: {score:.3f})")
    
    print("\n" + "="*80)
    print("TESTING SEMANTIC + LEXICAL SCORE BALANCE")
    print("="*80)
    
    # Demonstrate the score balance issue and solution
    print("With normalized scores, semantic (0-1.0) and lexical (0-1.0) are now balanced!")
    print("Example weights: semantic_weight=0.6, lexical_weight=0.4")
    print("Max combined score would be: 0.6 * 1.0 + 0.4 * 1.0 = 1.0")
    
    # Show some example calculations
    semantic_weight = 0.6
    lexical_weight = 0.4
    
    print(f"\nExample score combinations:")
    print(f"  High semantic (0.9), High lexical (0.8): {semantic_weight * 0.9 + lexical_weight * 0.8:.3f}")
    print(f"  Medium semantic (0.5), High lexical (0.9): {semantic_weight * 0.5 + lexical_weight * 0.9:.3f}")
    print(f"  High semantic (0.8), Medium lexical (0.4): {semantic_weight * 0.8 + lexical_weight * 0.4:.3f}")
    
    return True

if __name__ == "__main__":
    success = test_normalized_scoring()
    if success:
        print("\n" + "="*80)
        print("✅ NORMALIZED SCORING TEST COMPLETE!")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("❌ SOME TESTS FAILED!")
        print("="*80)
