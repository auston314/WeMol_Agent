import asyncio
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from anthropic import Anthropic
from openai import OpenAI

from mcp import ClientSession, Tool
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

load_dotenv()  # load environment variables from .env

class LLMResponse:
    def __init__(self, role: str, content: Any, stop_reason: Optional[str] = None):
        self.role = role
        self.content = content
        self.stop_reason = stop_reason

class MultiServerMCPClient:
    def __init__(
        self,
        provider: str,
        azure_config: Optional[Dict[str, Any]] = None,
    ):
        self.sessions: Dict[str, ClientSession] = {}
        self.tool_to_session: Dict[str, ClientSession] = {}
        self.all_tools: List[Dict[str, Any]] = []
        self.exit_stack = AsyncExitStack()
        self.connected: List[str] = []
        self.claude_model = "claude-3-7-sonnet-latest"

        self.provider = provider.lower()
        if self.provider == "azure":
            if not azure_config:
                raise ValueError("Azure provider requires azure_config")
            self.llm = OpenAI()
            self.azure_model = "gpt-4o"
            self.all_functions: Optional[List[Dict[str, Any]]] = None
        else:
            self.llm = Anthropic()

    async def connect_to_servers(self, servers: Dict[str, Dict[str, Any]]):
        """
        servers: {
          "<name>": {
             // for SSE-only:
             "url": "http://…/sse"
             // or for STDIO:
             "command": "/full/path/to/python",
             "args": ["…","…"]
          },
          …
        }
        """
        print("🔗 Connecting to MCP servers:")
        aggregated: List[Tool] = []

        for name, info in servers.items():
            url = info.get("url")
            print(f"  • {name}")
            try:
                if url:
                    # —— SSE Mode —— (exactly as original)
                    print(f"      SSE → {url}")
                    receive, send = await self.exit_stack.enter_async_context(
                        sse_client(url=url)
                    )
                else:
                    # —— STDIO Mode ——
                    cmd = info["command"]
                    args = info.get("args", [])
                    print(f"      STDIO → {cmd} {args}")
                    params = StdioServerParameters(
                        command=cmd,
                        args=args,
                        env=None
                    )
                    receive, send = await self.exit_stack.enter_async_context(
                        stdio_client(params)
                    )

                # wrap into MCP session
                session = await self.exit_stack.enter_async_context(
                    ClientSession(receive, send)
                )
                await session.initialize()

                # discover and register tools
                resp = await session.list_tools()
                tool_names = [t.name for t in resp.tools]
                print(f"    → Tools on {name}: {tool_names}")

                self.sessions[name] = session
                self.connected.append(name)
                for t in resp.tools:
                    if t.name in self.tool_to_session:
                        print(f"    ⚠️ Overwriting tool {t.name}")
                    self.tool_to_session[t.name] = session
                    aggregated.append(t)

            except Exception as exc:
                print(f"    ✖ Failed to connect {name}: {exc}")

        if not self.sessions:
            raise ConnectionError("No MCP servers connected!")

        # Prepare Anthropic tools list
        self.all_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
            for t in aggregated
        ]
        print(f"\n✅ Connected to {len(self.connected)} server(s).")
        print("   Available tools:", list(self.tool_to_session.keys()))

        # Prepare OpenAI function schemas
        if self.provider == "azure":
            self.all_functions = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in aggregated
            ]

    async def process_query(self, query: str) -> str:
        if not self.sessions:
            return "Error: no MCP servers connected."

        messages: List[Dict[str, Any]] = [{"role": "user", "content": query}, {"role": "user", "content": "Don't repeat the same tool calls multiple times if it is not necessary"}]
        output_parts: List[str] = []
        tool_log: List[Dict[str, Any]] = []

        # —— Anthropic branch —— 
        if self.provider == "anthropic":
            resp_raw = self.llm.messages.create(
                model=self.claude_model,
                max_tokens=1500,
                messages=messages,
                tools=self.all_tools or None,
                temperature=0.0,
            )
            resp = LLMResponse(resp_raw.role, resp_raw.content, resp_raw.stop_reason)
            messages.append({"role": resp.role, "content": resp.content})

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
                                out = "".join(getattr(c, "text", "") for c in (result.content or []))
                                calls.append({"type": "tool_result", "tool_use_id": cid, "content": out})
                                tool_log.append({"tool": name, "input": args, "output": out})
                            except Exception as e:
                                err = f"Error: {e}"
                                calls.append({"type": "tool_result", "tool_use_id": cid, "content": err, "is_error": True})
                                tool_log.append({"tool": name, "input": args, "error": str(e)})
                if not calls:
                    break

                messages.append({"role": "user", "content": calls})
                resp_raw = self.llm.messages.create(
                    model=self.claude_model,
                    max_tokens=1500,
                    messages=messages,
                    tools=self.all_tools or None,
                    temperature=0.0,
                )
                resp = LLMResponse(resp_raw.role, resp_raw.content, resp_raw.stop_reason)
                messages.append({"role": resp.role, "content": resp.content})

            for block in (resp.content or []):
                if block.type == "text":
                    output_parts.append(block.text)

            final = "\n".join(output_parts)
            if tool_log:
                final += "\n\n--- Tool Calls ---"
                for tr in tool_log:
                    res = tr.get("output", f"Error: {tr.get('error')}")
                    final += f"\n• {tr['tool']}({tr['input']}) → {res}"
                final += "\n-----------------"
            return final

        # —— Azure‐OpenAI branch —— 
        else:
            tools = self.all_functions
            resp_raw = self.llm.chat.completions.create(
                messages=messages,
                model=self.azure_model,
                tools=tools or None,
                temperature = 0.0
            )
            msg = resp_raw.choices[0].message
            azure_resp = LLMResponse(msg.role, msg.content, resp_raw.choices[0].finish_reason)

            final_output = ""
            while azure_resp.stop_reason == "tool_calls":
                calls: List[Dict[str, Any]] = []
                for tc in msg.tool_calls:
                    if tc.type == "function":
                        name = tc.function.name
                        args = json.loads(tc.function.arguments)
                        cid = tc.id
                        print(f"    ▶ Function call: {name}({args})")
                        if name in self.tool_to_session:
                            try:
                                result = await self.tool_to_session[name].call_tool(name, args)
                                out = "".join(getattr(c, "text", "") for c in (result.content or []))
                                calls.append({"type": "tool_result", "tool_use_id": cid, "content": out})
                                final_output += out + "\n"
                            except Exception as e:
                                calls.append({"type": "tool_result", "tool_use_id": cid, "content": f"Error: {e}"})
                if not calls:
                    break

                messages.append({"role": "assistant", "content": str(calls)})
                resp_raw = self.llm.chat.completions.create(
                    messages=messages,
                    model=self.azure_model,
                    tools=tools or None,
                    temperature=0.0
                )
                msg = resp_raw.choices[0].message
                azure_resp = LLMResponse(msg.role, msg.content, resp_raw.choices[0].finish_reason)
                if azure_resp.content:
                    messages.append({"role": azure_resp.role, "content": azure_resp.content})

            return final_output

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
                print("\nLLM response:\n", ans)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)

    async def cleanup(self):
        print("\n🧹 Cleaning up...")
        await self.exit_stack.aclose()

async def main():
    parser = argparse.ArgumentParser(description="Multi-Server MCP Client")
    parser.add_argument(
        "--config", "-c", type=Path, required=True,
        help="JSON file listing MCP servers (either `url` for SSE or `command`+`args` for STDIO)"
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["anthropic", "azure"],
        default="anthropic",
        help="Which LLM backend to use"
    )
    args = parser.parse_args()

    cfg = json.loads(args.config.read_text())
    servers = cfg.get("mcpServers", {})
    if not servers:
        print(f"No servers in {args.config}", file=sys.stderr)
        sys.exit(1)

    azure_config = {"timeout": 600} if args.provider == "azure" else None
    client = MultiServerMCPClient(provider=args.provider, azure_config=azure_config)

    try:
        await client.connect_to_servers(servers)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

