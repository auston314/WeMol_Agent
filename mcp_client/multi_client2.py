import asyncio
import sys
import yaml
import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, Tool
from mcp.client.sse import sse_client               # SSE transport for MCP
from anthropic import Anthropic
import httpx
import openai
from openai import AzureOpenAI, OpenAI
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

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
        self.claude_model0 = "claude-3-5-sonnet-20240620"
        self.claude_model = "claude-3-7-sonnet-latest"

        self.provider = provider.lower()
        if self.provider == "azure":
            if not azure_config:
                raise ValueError("Azure provider requires azure_config")
            # http_client = httpx.Client(verify=azure_config.get("verify", True))
            # credential = DefaultAzureCredential()
            # def azure_token_provider() -> str:
            #     tok = credential.get_token("https://cognitiveservices.azure.com/.default")
            #     return tok.token

            # self.llm = AzureOpenAI(
            #     api_version=azure_config["api_version"],
            #     azure_endpoint=azure_config["azure_endpoint"],
            #     azure_ad_token_provider=azure_token_provider,
            #     http_client=http_client,
            #     timeout=azure_config.get("timeout", 600),
            #     max_retries=azure_config.get("max_retries", 5),
            # )
            # self.azure_model = azure_config.get("model")
            self.llm = OpenAI()
            self.azure_model = "gpt-4o"
            # will be populated after connect_to_servers()
            self.all_functions: Optional[List[Dict[str, Any]]] = None

        else:
            self.llm = Anthropic()

    async def connect_to_servers(self, server_urls: List[str]):
        print("🔗 Connecting to MCP servers:")
        aggregated: List[Tool] = []

        for url in server_urls:
            print(f"  • {url}")
            try:
                receive, send = await self.exit_stack.enter_async_context(
                    sse_client(url=url)
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

        # Prepare Anthropic tools payload
        self.all_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
            for t in aggregated
        ]
        print(f"\n✅ Connected to {len(self.connected)} server(s).")
        print("   Available tools:", list(self.tool_to_session.keys()))

        # Prepare OpenAI functions payload
        if self.provider == "azure":
            self.all_functions = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                }
                for t in self.all_tools
            ]

    async def process_query(self, query: str) -> str:
        if not self.sessions:
            return "Error: no MCP servers connected."

        messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]
        output_parts: List[str] = []
        tool_log: List[Dict[str, Any]] = []
        #print("Process query:", query)
        # -------- Anthropic branch --------
        if self.provider == "anthropic":
            resp_raw = self.llm.messages.create(
                model=self.claude_model,
                max_tokens=1500,
                messages=messages,
                tools=(self.all_tools or None),
            )
            resp = LLMResponse(resp_raw.role, resp_raw.content, resp_raw.stop_reason)
            #print("resp = ", resp)
            if not resp.content:
                raise ValueError("No response from Anthropic")
            if resp.stop_reason == "function_call":
                raise ValueError("Function call not supported in this branch")
            #print("resp.content = ", resp.content)

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
                                text_out = "".join(getattr(c, "text", "") for c in (result.content or []))
                                calls.append({"type": "tool_result", "tool_use_id": cid, "content": text_out})
                                tool_log.append({"tool": name, "input": args, "output": text_out})
                            except Exception as e:
                                err = f"Error: {e}"
                                calls.append({"type": "tool_result", "tool_use_id": cid, "content": err, "is_error": True})
                                tool_log.append({"tool": name, "input": args, "error": str(e)})
                        else:
                            err = f"Tool {name} not found"
                            calls.append({"type": "tool_result", "tool_use_id": cid, "content": err, "is_error": True})
                            tool_log.append({"tool": name, "input": args, "error": "not_found"})

                if not calls:
                    break

                messages.append({"role": "user", "content": calls})
                resp_raw = self.llm.messages.create(
                    model=self.claude_model,
                    max_tokens=1500,
                    messages=messages,
                    tools=(self.all_tools or None),
                )
                resp = LLMResponse(resp_raw.role, resp_raw.content, resp_raw.stop_reason)       
                #print("resp = ", resp)
                messages.append({"role": resp.role, "content": resp.content})

            for block in resp.content or []:
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

        # -------- Azure‐OpenAI branch with functions --------
        else:
            #print("OpenAI branch goes here ...............")
            # Hardcoded for now
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "get_current_time",
                        "description": "Get the local date and time in ISO 8601 format.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "check_student_gpa",
                        "description": "Check a student's GPA by student's name. Return 0 if not found.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "student_name": {
                                     "type": "string",
                                     "description": "The name of the student, eg. John Doe.",
                                },
                            },
                        },
                        "required": ["student_name"],
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "off_school_request",
                        "description": "Off school request with off type, start date and end date for the off_school",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "off_type": {
                                    "type": "string",
                                    "description": "The type of off school, eg. sick time, field trip or college visit.",
                                    "enum": ["sick time", "field trip", "college visit"],
                                },
                                "start_date": {
                                    "type": "string", 
                                    "description": "The start date of the off school, eg. 2025-04-27.",
                                },
                                "end_date": {
                                    "type": "string",
                                    "description": "The end date of the off school, eg. 2025-04-30.",
                                },
                            },
                            "required": ["off_type","start_date", "end_date"],
                        },
                    },
                },                 
            ]   
            azure_kwargs: Dict[str, Any] = {}
            if self.azure_model:
                azure_kwargs["deployment_id"] = self.azure_model

            functions = self.all_functions or None

            # print("model = ", self.azure_model)
            # print("functions = ", functions)
            # print("messages = ", messages)
            model = "gpt-4o"
            # print("all_functions = ", self.all_functions)
            # print("all_tools = ", self.all_tools)
            # initial request
            resp_raw = self.llm.chat.completions.create(
                messages=messages,
                model = model,
                tools = tools,
            )
            msg = resp_raw.choices[0].message
            #print("msg = ", msg)
            azure_resp = LLMResponse(msg.role, msg.content, resp_raw.choices[0].finish_reason)

            final_output = ""
            while (azure_resp.stop_reason == "tool_calls"):
                # Find the tools in the response
                msg = resp_raw.choices[0].message
                print("Tool calls found in the response", msg.tool_calls)
                calls: List[Dict[str, Any]] = []

                for tool_call in msg.tool_calls:
                    print("Tool call = ", tool_call)
                    if tool_call.type == "function":
                        name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments)
                        print(f"    ▶ Function call: {name} {args!r}")
                        cid = tool_call.id
                        if name in self.tool_to_session:
                            try:
                                result = await self.tool_to_session[name].call_tool(name, args)
                                print("result = ", result)
                                text_out = "".join(getattr(c, "text", "") for c in (result.content or []))
                                calls.append({"type": "tool_result", "tool_use_id": cid, "content": text_out})
                                tool_log.append({"tool": name, "input": args, "output": text_out})
                                final_output += text_out + "\n"
                            except Exception as e:
                                #print(f"Error calling tool {name}: {e}")
                                text_out = f"Error: {e}"
                        else:
                            text_out = f"Tool {name} not found"

                        tool_log.append({"tool": name, "input": args, "output": text_out})
                if not calls:
                    #print("No calls found, break")
                    break

                print("text_out = ", text_out)
                print("Make final LLM call")
                print("calls = ", calls)
                if (calls):
                    messages.append({"role": "assistant", "content": str(calls)})
                print("messages = ", len(messages))
                print("model = ", model)
                print("messages = ", messages)
                print("tools = ", tools)
                #messages.append({"role": "user", "content": "Give me the final answer based on the provided context"})
                try:
                    resp_raw = self.llm.chat.completions.create(
                        model=model,
                        max_tokens=1500,
                        messages=messages,
                        tools=(tools or None),
                    )
                    print("resp_raw = ", resp_raw)
                    msg = resp_raw.choices[0].message
                    azure_resp = LLMResponse(msg.role, msg.content, resp_raw.choices[0].finish_reason)
                    print("azure_resp = ", azure_resp)
                    #azure_resp = LLMResponse(resp_raw.role, resp_raw.content, resp_raw.stop_reason)
                    if(azure_resp.content):
                        messages.append({"role": azure_resp.role, "content": azure_resp.content})
                except Exception as e:
                    print(f"Error calling LLM: {e}")
                    break
                #print("azure_resp = ", azure_resp)

            # output_parts.append(azure_resp.content)
            # #print("output_parts = ", output_parts)
            # final = "\n".join(output_parts)
            # if tool_log:
            #     final += "\n\n--- Tool Calls ---"
            #     for tr in tool_log:
            #         res = tr.get("output", f"Error: {tr.get('error')}")
            #         final += f"\n• {tr['tool']}({tr['input']}) → {res}"
            #     final += "\n-----------------"
            print("final = ", final_output)
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
        help="YAML file listing MCP servers and (for Azure) LLM settings"
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["anthropic", "azure"],
        default="anthropic",
        help="Which LLM backend to use"
    )
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    servers = cfg.get("mcp_servers", [])
    if not servers:
        print(f"No servers in {args.config}", file=sys.stderr)
        sys.exit(1)

    azure_config = None
    if args.provider == "azure":
        azure_config = {"timeout": 600}
        # azure_config = {
        #     "azure_endpoint": cfg["azure_endpoint"],
        #     "api_version": cfg["azure_api_version"],
        #     "verify": cfg.get("azure_verify", True),
        #     "model": cfg.get("azure_model"),
        #     "timeout": cfg.get("azure_timeout", 600),
        #     "max_retries": cfg.get("azure_max_retries", 5),
        # }

    client = MultiServerMCPClient(provider=args.provider, azure_config=azure_config)
    try:
        await client.connect_to_servers(servers)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
