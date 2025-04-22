#!/usr/bin/env python3
import asyncio
import sys
import yaml
import argparse
from pathlib import Path
from typing import Dict, List, Any
from contextlib import AsyncExitStack

from mcp import ClientSession, Tool
from mcp.client.sse import sse_client               # SSE transport for MCP :contentReference[oaicite:0]{index=0}
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # load API keys, e.g. ANTHROPIC_API_KEY

class MultiServerMCPClient:
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.tool_to_session: Dict[str, ClientSession] = {}
        self.all_tools: List[Dict[str, Any]] = []
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
        self.connected: List[str] = []

    async def connect_to_servers(self, server_urls: List[str]):
        """Connect to each remote SSE-based MCP server."""
        print("🔗 Connecting to MCP servers:")
        aggregated: List[Tool] = []

        for url in server_urls:
            print(f"  • {url}")
            try:
                receive, send = await self.exit_stack.enter_async_context(
                    sse_client(url=url)   # GET /sse + POST /messages :contentReference[oaicite:1]{index=1}
                )
                session = await self.exit_stack.enter_async_context(
                    ClientSession(receive, send)
                )
                await session.initialize()

                resp = await session.list_tools()
                names = [t.name for t in resp.tools]
                print(f"    → Tools: {names}")

                self.sessions[url] = session
                self.connected.append(url)
                for t in resp.tools:
                    if t.name in self.tool_to_session:
                        print(f"    ⚠️ Overwriting tool {t.name}")
                    self.tool_to_session[t.name] = session
                    aggregated.append(t)

            except Exception as e:
                print(f"    ✖ Failed: {e}")

        if not self.sessions:
            raise ConnectionError("No MCP servers connected!")

        # Prepare for Claude
        self.all_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
            for t in aggregated
        ]
        print(f"\n✅ Connected to {len(self.connected)} server(s).")
        print("   Available tools:", list(self.tool_to_session.keys()))

    async def process_query(self, query: str) -> str:
        """Send query to Claude, loop over any tool_use, and return final answer."""
        if not self.sessions:
            return "Error: no MCP servers connected."

        tools_payload = self.all_tools or None
        messages = [{"role": "user", "content": query}]
        output_parts: List[str] = []
        history: List[Dict[str, Any]] = []
        tool_log: List[Dict[str, Any]] = []

        # First Claude call
        resp = self.anthropic.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1500,
            messages=messages,
            tools=tools_payload
        )
        messages.append({"role": resp.role, "content": resp.content})

        # Handle tool_use loops
        while resp.stop_reason == "tool_use":
            calls: List[Dict[str, Any]] = []

            for block in resp.content:
                if block.type == "text":
                    output_parts.append(block.text)
                elif block.type == "tool_use":
                    name, args, cid = block.name, block.input, block.id
                    print(f"    ▶ Tool call: {name}({args})")

                    if name in self.tool_to_session:
                        try:
                            result = await self.tool_to_session[name].call_tool(name, args)
                            text_out = "".join(getattr(c, "text", "") for c in (result.content or []))
                            print(f"    ◀ Result: {text_out!r}")
                            calls.append({"type": "tool_result", "tool_use_id": cid, "content": text_out})
                            tool_log.append({"tool": name, "input": args, "output": text_out})
                        except Exception as e:
                            err = f"Error: {e}"
                            print(f"    !! {err}")
                            calls.append({"type": "tool_result", "tool_use_id": cid, "content": err, "is_error": True})
                            tool_log.append({"tool": name, "input": args, "error": str(e)})
                    else:
                        err = f"Tool {name} not found"
                        print(f"    !! {err}")
                        calls.append({"type": "tool_result", "tool_use_id": cid, "content": err, "is_error": True})
                        tool_log.append({"tool": name, "input": args, "error": "not_found"})

            if not calls:
                break

            messages.append({"role": "user", "content": calls})
            resp = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1500,
                messages=messages,
                tools=tools_payload
            )
            messages.append({"role": resp.role, "content": resp.content})

        # Collect final text
        for block in resp.content or []:
            if block.type == "text":
                output_parts.append(block.text)

        # Assemble
        final = "\n".join(output_parts)
        if tool_log:
            final += "\n\n--- Tool Calls ---"
            for tr in tool_log:
                res = tr.get("output", f"Error: {tr.get('error')}")
                final += f"\n• {tr['tool']}({tr['input']}) → {res}"
            final += "\n-----------------"
        return final

    async def chat_loop(self):
        print("\n💬 Enter queries (or 'quit' to exit):")
        while True:
            q = input("Query: ").strip()
            if q.lower() == "quit":
                break
            if not q:
                continue
            try:
                ans = await self.process_query(q)
                print("\nClaude:\n", ans)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)

    async def cleanup(self):
        print("\n🧹 Cleaning up...")
        await self.exit_stack.aclose()

async def main():
    # CLI: --config / -c to point at YAML file
    parser = argparse.ArgumentParser(description="Multi‑Server MCP Client")
    parser.add_argument(
        "--config", "-c",
        type=Path,
        required=True,
        help="YAML file listing mcp_servers endpoints"
    )
    args = parser.parse_args()

    # Load YAML
    cfg = yaml.safe_load(args.config.read_text())
    servers = cfg.get("mcp_servers", [])
    if not servers:
        print(f"No servers in {args.config}", file=sys.stderr)
        sys.exit(1)

    client = MultiServerMCPClient()
    try:
        await client.connect_to_servers(servers)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

