"""
General Chemistry Q&A MCP Server (SSE Version) - Answer chemistry questions using RAG

This MCP server provides question-answering capabilities for general chemistry
based on a pre-built content tree from a general chemistry textbook.

Features:
- Answer general chemistry questions using RAG (Retrieval-Augmented Generation)
- Get information about the knowledge base
- Adjust retrieval parameters (top_k results)
- Thread-safe content tree access

Port: 3002
Transport: SSE (Server-Sent Events)
"""

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn
import logging
import pickle
import os
import sys

# Add the mcp_kb directory to the Python path to import the required modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp_kb'))

from content_tree import ContentTree
from llm_client_adaptor import LLMClientAdaptor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("genchem_qa_sse_server")

# Global variables for the content tree and LLM client
content_tree = None
llm_client = None

# Initialize the content tree and LLM client
def initialize_server(model_name: str = "claude-haiku-4-5"):
    """Initialize the content tree from pickle file and create LLM client."""
    global content_tree, llm_client
    model_list = [("openai","gpt-5"), ("openai","gpt-5-mini"), ("openai", "gpt-4o"), ("openai", "gpt-4o-mini"), ("anthropic", "claude-sonnet-4-5"), ("anthropic", "claude-haiku-4-5")]
    # Path to the pickle file (in the mcp_kb directory)
    pickle_path = os.path.join(os.path.dirname(__file__), '..', 'mcp_kb', 'genchem_question_full.pkl')
    model_provider_dict = {}
    for provider, model in model_list:
        model_provider_dict[model] = provider
    
    provider = model_provider_dict.get(model_name, "")
    if not provider:
        logger.error(f"❌ Error: Model '{model_name}' is not recognized. Please check the model name.")
        raise ValueError(f"Model '{model_name}' is not recognized.")
    
    try:
        logger.info(f"Loading content tree from: {pickle_path}")
        with open(pickle_path, 'rb') as f:
            content_tree = pickle.load(f)
        logger.info("✅ Content tree loaded successfully")
        
        # Initialize the LLM client (using OpenAI GPT-4o)
        logger.info("Initializing LLM client (OpenAI GPT-4o)...")
        #llm_client = LLMClientAdaptor(provider="openai", model="gpt-4o")
        llm_client = LLMClientAdaptor(provider="anthropic", model="claude-haiku-4-5")
        # #llm_model = "claude-sonnet-4-5"
        # llm_model = "claude-haiku-4-5"
        logger.info("✅ LLM client initialized successfully")
        
    except FileNotFoundError:
        logger.error(f"❌ Error: Content tree pickle file not found at {pickle_path}")
        logger.error("Please ensure 'genchem_question_full.pkl' exists in the mcp_kb directory")
        raise
    except Exception as e:
        logger.error(f"❌ Error initializing server: {str(e)}")
        raise

# Initialize on module load
initialize_server()

# Create an MCP server with FastMCP
mcp = FastMCP("genchem_qa_server")

"""Answer a general chemistry question or find general chemistry related information using the RAG system.
    
    This tool searches through a comprehensive general chemistry content
    that has been pre-processed into a content tree structure with embeddings.
    It uses Retrieval-Augmented Generation (RAG) to find relevant content
    and generate accurate answers.
    
    The system:
    1. Searches for the most relevant sections in the content
    2. Retrieves content from the top-k most relevant nodes
    3. Generates an answer using GPT-4o based on the retrieved content
    
    Topics covered include:
    - Atomic structure and periodic table
    - Chemical bonding and molecular structure
    - Chemical reactions and stoichiometry
    - States of matter (gases, liquids, solids)
    - Solutions and concentrations
    - Thermodynamics and thermochemistry
    - Chemical kinetics
    - Chemical equilibrium
    - Acids and bases
    - Electrochemistry
    - And many more general chemistry topics
    
    Args:
        question: The chemistry related question or request (e.g., "What is a solution?",
                 "Explain the difference between ionic and covalent bonds",
                 "How do you calculate molarity?")
    
    Returns:
        A comprehensive answer based on the content, or a message
        indicating no relevant information was found.
    
    Examples:
        - "What is a solution?"
        - "Explain the ideal gas law"
        - "What are the properties of acids?"
        - "How do you balance chemical equations?"
        - "What is electronegativity?"
    """
@mcp.tool()
def answer_chemistry_question(question: str) -> str:
    """Answer any chemistry related question or find any chemistry related information.
    
    Args:
        question: The chemistry related question or request (e.g., "What is a solution?",
                 "Explain the difference between ionic and covalent bonds",
                 "How do you calculate molarity?")
    
    Returns:
        A comprehensive answer based on the content, or a message
        indicating no relevant information was found.
    
    """
    print("Answer chemistry question called with:", question)
    if not question or not question.strip():
        return "❌ Error: Please provide a valid chemistry question."
    
    # Validate top_k parameter
    top_k = 3  # Default value
    top_k = max(1, min(top_k, 5))  # Constrain between 1 and 5
    
    try:
        logger.info(f"📚 Processing question: {question}")
        logger.info(f"   Using top_k={top_k} content sections")
        
        # Use the RAG system to answer the question
        answer = content_tree.rag_query(
            user_query=question,
            top_k=top_k,
            llm_client_adaptor=llm_client,
            debug=True
        )
        
        print("Answer from RAG Query = ", answer)
        logger.info(f"✅ Answer generated successfully")
        
        # Format the response
        # response = f"🧪 General Chemistry Q&A\n"
        # response += "=" * 80 + "\n\n"
        # response += f"Question: {question}\n\n"
        # response += "-" * 80 + "\n\n"
        # response += f"Answer:\n{answer}\n\n"
        # response += "-" * 80 + "\n"
        # response += f"(Retrieved from top {top_k} most relevant section(s))\n"
        
       
        return "Answer to the question: " + answer
        
    except Exception as e:
        error_msg = f"❌ Error processing question: {str(e)}"
        logger.error(error_msg)
        return error_msg


#@mcp.tool()
def get_knowledge_base_info() -> str:
    """Get information about the general chemistry knowledge base.
    
    Returns:
        Information about the content tree structure, including:
        - Total number of content nodes
        - Knowledge base source
        - Available topics and coverage
        - System capabilities
    """
    try:
        # Count nodes in the tree
        all_nodes = list(content_tree.tree_node_iterator())
        total_nodes = len(all_nodes)
        
        # Get some sample topics from top-level headers
        top_level_headers = [node.header for node in all_nodes if node.header_level == 1][:10]
        
        info = "📚 GENERAL CHEMISTRY KNOWLEDGE BASE\n"
        info += "=" * 80 + "\n\n"
        info += "System Information:\n"
        info += "-" * 80 + "\n"
        info += f"  • Total content nodes: {total_nodes}\n"
        info += f"  • Top-level sections: {len(top_level_headers)}\n"
        info += f"  • LLM model: OpenAI GPT-4o\n"
        info += f"  • Search method: Hybrid (semantic + lexical)\n"
        info += f"  • Knowledge base: General Chemistry Textbook\n\n"
        
        info += "Sample Topics:\n"
        info += "-" * 80 + "\n"
        for header in top_level_headers[:8]:
            info += f"  • {header}\n"
        if len(top_level_headers) > 8:
            info += f"  • ... and {len(top_level_headers) - 8} more\n"
        
        info += "\n" + "-" * 80 + "\n"
        info += "Capabilities:\n"
        info += "  ✓ Answer conceptual chemistry questions\n"
        info += "  ✓ Explain chemical principles and theories\n"
        info += "  ✓ Define chemistry terms and concepts\n"
        info += "  ✓ Describe chemical reactions and processes\n"
        info += "  ✓ Provide information on chemical properties\n\n"
        
        info += "Usage:\n"
        info += "  Use 'answer_chemistry_question' to ask any general chemistry question.\n"
        info += "  Adjust 'top_k' parameter to control how many content sections to retrieve.\n\n"
        
        info += "=" * 80 + "\n"
        
        return info
        
    except Exception as e:
        return f"❌ Error retrieving knowledge base info: {str(e)}"


#@mcp.tool()
def get_example_questions() -> str:
    """Get example questions that can be asked to the system.
    
    Returns:
        A list of example chemistry questions organized by topic.
    """
    examples = "💡 EXAMPLE CHEMISTRY QUESTIONS\n"
    examples += "=" * 80 + "\n\n"
    
    examples += "Basic Concepts:\n"
    examples += "  • What is matter?\n"
    examples += "  • What is the difference between an element and a compound?\n"
    examples += "  • What is a chemical reaction?\n"
    examples += "  • What is the periodic table?\n\n"
    
    examples += "Atomic Structure:\n"
    examples += "  • What are the parts of an atom?\n"
    examples += "  • What is an electron configuration?\n"
    examples += "  • What are isotopes?\n"
    examples += "  • What is atomic number and mass number?\n\n"
    
    examples += "Chemical Bonding:\n"
    examples += "  • What is an ionic bond?\n"
    examples += "  • What is a covalent bond?\n"
    examples += "  • What is electronegativity?\n"
    examples += "  • What are Lewis structures?\n\n"
    
    examples += "States of Matter:\n"
    examples += "  • What are the properties of gases?\n"
    examples += "  • What is the ideal gas law?\n"
    examples += "  • What is vapor pressure?\n"
    examples += "  • What are intermolecular forces?\n\n"
    
    examples += "Solutions:\n"
    examples += "  • What is a solution?\n"
    examples += "  • What is molarity?\n"
    examples += "  • What is solubility?\n"
    examples += "  • What is osmotic pressure?\n\n"
    
    examples += "Chemical Reactions:\n"
    examples += "  • How do you balance chemical equations?\n"
    examples += "  • What is stoichiometry?\n"
    examples += "  • What is a limiting reactant?\n"
    examples += "  • What are oxidation-reduction reactions?\n\n"
    
    examples += "Thermodynamics:\n"
    examples += "  • What is enthalpy?\n"
    examples += "  • What is entropy?\n"
    examples += "  • What is Gibbs free energy?\n"
    examples += "  • What is Hess's law?\n\n"
    
    examples += "Acids and Bases:\n"
    examples += "  • What is pH?\n"
    examples += "  • What is a buffer solution?\n"
    examples += "  • What are strong and weak acids?\n"
    examples += "  • What is the Bronsted-Lowry theory?\n\n"
    
    examples += "=" * 80 + "\n"
    examples += "Try any of these questions with 'answer_chemistry_question'!\n"
    
    return examples


#@mcp.tool()
def search_topics(keyword: str, max_results: int = 10) -> str:
    """Search for topics in the knowledge base that contain a specific keyword.
    
    This tool performs a simple text search through all section headers
    to help you discover what topics are covered in the knowledge base.
    
    Args:
        keyword: The keyword to search for (e.g., "bond", "reaction", "gas")
        max_results: Maximum number of results to return (default: 10, max: 50)
    
    Returns:
        List of matching topic headers with their content preview.
    """
    if not keyword or not keyword.strip():
        return "❌ Error: Please provide a valid keyword to search."
    
    # Validate max_results
    max_results = max(1, min(max_results, 50))
    
    try:
        keyword_lower = keyword.lower()
        all_nodes = list(content_tree.tree_node_iterator())
        
        # Find nodes with matching headers
        matching_nodes = [
            node for node in all_nodes
            if keyword_lower in node.header.lower()
        ]
        
        if not matching_nodes:
            return f"No topics found containing '{keyword}'. Try a different keyword."
        
        # Limit results
        matching_nodes = matching_nodes[:max_results]
        
        result = f"🔍 SEARCH RESULTS FOR: '{keyword}'\n"
        result += "=" * 80 + "\n\n"
        result += f"Found {len(matching_nodes)} matching topic(s):\n\n"
        
        for i, node in enumerate(matching_nodes, 1):
            indent = "  " * (node.header_level - 1)
            result += f"{i}. {indent}{node.header}\n"
            
            # Add content preview if available
            if node.content_text:
                preview = node.content_text[:150].replace('\n', ' ').strip()
                if len(node.content_text) > 150:
                    preview += "..."
                result += f"   Preview: {preview}\n"
            result += "\n"
        
        if len(matching_nodes) >= max_results:
            result += f"(Showing first {max_results} results. Use max_results parameter to see more.)\n"
        
        result += "=" * 80 + "\n"
        result += "Use 'answer_chemistry_question' to ask questions about these topics.\n"
        
        return result
        
    except Exception as e:
        return f"❌ Error searching topics: {str(e)}"


# Mount the MCP SSE app at root
app = Starlette(routes=[
    Mount("/", app=mcp.sse_app()),
])

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("🧪 Starting General Chemistry Q&A MCP Server (SSE) on port 3002...")
    logger.info("=" * 80)
    logger.info("Knowledge Base: General Chemistry Textbook (Content Tree)")
    logger.info("LLM Model: OpenAI GPT-4o")
    logger.info("Available tools:")
    logger.info("  • answer_chemistry_question - Answer general chemistry questions")
    logger.info("  • get_knowledge_base_info - Get info about the knowledge base")
    logger.info("  • get_example_questions - Get example questions to ask")
    logger.info("  • search_topics - Search for topics by keyword")
    logger.info("=" * 80)
    
    # Listen on all interfaces, port 3002
    uvicorn.run(app, host="0.0.0.0", port=3002)
