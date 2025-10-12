import asyncio
import sys
import json
import argparse
from datetime import datetime
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

class MCPHost:
    def __init__(
        self,
        provider: str,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        self.sessions: Dict[str, ClientSession] = {}
        self.tool_to_session: Dict[str, ClientSession] = {}
        self.all_tools: List[Dict[str, Any]] = []
        self.exit_stack = AsyncExitStack()
        self.connected: List[str] = []
        self.claude_model = "claude-3-7-sonnet-latest"

        self.provider = provider.lower()
        if self.provider == "openai":
            if not llm_config:
                raise ValueError("OpenAI provider requires llm_config")
            self.llm = OpenAI()
            self.openai_model = "gpt-4o"
            self.all_functions: Optional[List[Dict[str, Any]]] = None
        else:
            self.llm = Anthropic()

    async def connect_mcp_servers(self, servers: Dict[str, Dict[str, Any]]):
        """
        MCP server configuration example:
        {
            "mcpServers": {
                # server1: STDIO mode
                "server1": {
                    "command": "full_path_to_python",
                    "args": ["full_path_to_mcp_server.py"]
                },
                # server2: SSE mode
                "server2": {
                    "url": "http://localhost:8001/sse"
                }
            }
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
        if self.provider == "openai":
            self.all_tools = [
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

    async def process_query(self, query: str, chat_history: list = [], user_name: str = "James Lee") -> str:
        if not self.sessions:
            return "Error: No MCP servers connected."

        user_context = {"role":"system","content":f"User name: {user_name}, Today's date is {datetime.now().isoformat()[:16]}"}
        messages: List[Dict[str, Any]] = [user_context] + chat_history[-4:] # Last 4 messages, include the last user message (query)
        output_parts: List[str] = []
        tool_log: List[Dict[str, Any]] = []

        # —— Anthropic branch —— 
        if self.provider == "anthropic":
            try:
                resp_raw = self.llm.messages.create(
                    model=self.claude_model,
                    max_tokens=1500,
                    messages=messages,
                    tools=self.all_tools or None,
                    temperature=0.0,
                )
                messages.append({"role": resp_raw.role, "content": resp_raw.content})

                while resp_raw.stop_reason == "tool_use":
                    calls: List[Dict[str, Any]] = []
                    for block in resp_raw.content:
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
                    messages.append({"role": resp_raw.role, "content": resp_raw.content})
                for block in (resp_raw.content or []):
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

            except Exception as e:
                return f"Error: {e}"

        # —— OpenAI branch —— 
        else:
            tools = self.all_tools
            response = self.llm.chat.completions.create(
                messages=messages,
                model=self.openai_model,
                tools=tools or None,
                tool_choice = "auto",
                temperature = 0.0
            )

            choice0 = response.choices[0]

            stop_reason = response.choices[0].finish_reason
            msg = response.choices[0].message
            messages.append(msg.model_dump())
            final_output = ""
            tc_count = 0
            if (response.choices[0].message.content):
                final_output = response.choices[0].message.content
            max_turns = 5
            turn = 0
            tc_count = 0
            while stop_reason == "tool_calls" and turn < max_turns:
                turn += 1
                calls: List[Dict[str, Any]] = []
                tc_count = 0
                for tc in msg.tool_calls:
                    if tc.type == "function":
                        name = tc.function.name
                        #args = json.loads(tc.function.arguments)
                        args = eval(tc.function.arguments)
                        cid = tc.id
                        print(f"    ▶ Function call: {name}({args})")
                        if name in self.tool_to_session:
                            try:
                                result = await self.tool_to_session[name].call_tool(name, args)
                                tc_count += 1
                                tc_message = {
                                    "tool_call_id": cid,
                                    "role": "tool",
                                    "name": name,
                                    "content": result.content[0].text
                                }
                                messages.append(tc_message)
                                #tool_log.append({"tool": name, "input": args, "output": tc_message["content"]}
                            except Exception as e:
                                print(f"Error {e}")
       
                if tc_count == 0:
                    break
                
                # Prepare for the response based on the tool calls
                response = self.llm.chat.completions.create(
                    messages=messages,
                    model=self.openai_model,
                    tools=tools or None,
                )
                stop_reason = response.choices[0].finish_reason
                msg = response.choices[0].message
                messages.append(msg.model_dump())

                if stop_reason == "stop":
                    break

            if (tc_count > 0 and response.choices[0].message.content):
                if (final_output != ""):
                    final_output += "<br>\n" + response.choices[0].message.content
                else:
                    final_output = response.choices[0].message.content

            final_output = final_output.replace("\\(","$").replace("\\)","$").replace("\\[","$$").replace("\\]","$$")
            print("Final output = ", final_output)
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
    parser = argparse.ArgumentParser(description="Multi-Server MCP Host")
    parser.add_argument(
        "--config", "-c", type=Path, required=True,
        help="JSON file listing MCP servers (either `url` for SSE or `command`+`args` for STDIO)"
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["anthropic", "openai"],
        default="anthropic",
        help="Which LLM backend to use"
    )
    args = parser.parse_args()

    cfg = json.loads(args.config.read_text())
    servers = cfg.get("mcpServers", {})
    if not servers:
        print(f"No servers in {args.config}", file=sys.stderr)
        sys.exit(1)

    llm_config = {"timeout": 600} if args.provider == "openai" else None
    client = MCPHost(provider=args.provider, llm_config=llm_config)

    try:
        await client.connect_mcp_servers(servers)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

