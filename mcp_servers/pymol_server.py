# server.py
import chatmol as cm
from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage

# Create an MCP server
mcp = FastMCP("Pymol")

defaul_client = cm.ChatMol()
pymolserver = cm.PymolServer(defaul_client)

@mcp.tool()
def open_pymol():
    """open pymol"""
    pymolserver.start_pymol()
    return "Pymol opened"


@mcp.tool()
def run_pymol_command(command: str):
    """run pymol command"""
    pymolserver.server.do(command)
    return "Command executed"

@mcp.tool()
def save_imgae(file_path: str):
    """save current view of pymol session to a file, perferably .png"""
    pymolserver.server.do(f"zoom; png ~/{file_path}, dpi=75")
    return f"File saved at ~/{file_path}"
    # return file_path


# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
