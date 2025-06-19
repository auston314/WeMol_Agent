# server.py
import subprocess
from mcp.server.fastmcp import FastMCP, Image
from xmlrpc.client import ServerProxy
from glob import glob

# Create an MCP server
mcp = FastMCP("chimerax")
xmlrpc_port = 42184
s = ServerProxy(uri="http://127.0.0.1:%d/RPC2" % xmlrpc_port)

@mcp.tool()
def start_chimerax():
    """Start ChimeraX with remote control enabled. ChimeraX is a molecular visualization tool. It has very rich functionality for various molecular operations, such as 3D visualization of both small and large protein molecules."""
    # Check if ChimeraX is already running
    try:
        # Try to run a simple command
        s.run_command("version")
        return "ChimeraX is already running."
    except Exception:
        # ChimeraX is not running, so start it
        chimerax_bin = "/Applications/ChimeraX*.app/Contents/bin/ChimeraX"
        chimerax_bin = glob(chimerax_bin)[0]
        cmds = [
            chimerax_bin,
            "--cmd",
            "'remotecontrol xmlrpc true'"
        ]
        subprocess.Popen(
                " ".join(cmds),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True,
                bufsize=1,  # Line-buffered
                universal_newlines=True
            )
        return "ChimeraX has been successfully started."

@mcp.tool()
def run_chimerax_command(command: str):
    """run chimerax command for various 3D molecular visualization, protein sequence display and other operations. """
    s.run_command(command)
    return f"ChimeraX command {command} has been executed sussefully. {s.run_command(command)}"

if __name__ == "__main__":
    mcp.run()
