# WeMol_Agent
WeMol Agent is a generic agent framework based on MCP client/server and multi-agents orchestration using Large Language Models. 

* Both Claude models and OpenAI models are supported. 

* MCP servers with both STDIO and SSE connections are supported.
* Plug and Play for adding MCP servers into a configuration JSON file. For example:
```
{
  "mcpServers": {
    "time_date_server": {
      "command": "<your_full_path_to_python>",
      "args": [
        "<your_full_path_to_server_python_script.py>"
      ]
    },
    "gpa_server": {
       "url": "http://localhost:3000/sse"
    }
  }
}
``` 

 
