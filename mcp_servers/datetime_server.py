from mcp.server.fastmcp import FastMCP
from datetime import datetime
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn


mcp = FastMCP("time_date_server")

@mcp.tool()
def get_current_time():
    """Get the local date and time in ISO 8601 format."""
    return "The local time and date is " + datetime.now().isoformat()


# Mount the MCP SSE app at root
app = Starlette(routes=[
    Mount("/", app=mcp.sse_app()),
])

if __name__ == "__main__":
    # Listen on all interfaces, port 3001
    uvicorn.run(app, host="0.0.0.0", port=3001)

