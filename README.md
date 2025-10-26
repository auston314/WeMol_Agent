# WeMol Agent
AI powered tutor for higher education based on MCP client/server and multi-agents orchestration. 

* Both Claude models and OpenAI models are supported. 

* MCP servers with both STDIO and SSE connections are supported.
* Plug and Play for adding MCP servers into a configuration JSON file. For example:
```
{
  "mcpServers": {
    "database_sql_server": {
       "url": "http://localhost:3001/sse"
    },
    "genchem_qa_server": {
       "url": "http://localhost:3002/sse"
    },
    "conformation_server": {
       "url": "http://localhost:3003/sse"
    }
  }
}
``` 

 
