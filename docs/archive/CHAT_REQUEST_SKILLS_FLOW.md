# Chat Request Flow and Skill Usage

This document shows the runtime path for a chat request from the React UI to the RAG backend, and where MCP skills fit.

## Mermaid Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant FE as React Chat UI (App.js)
    participant API as FastAPI (/v1/chat/completions)
    participant AG as StrandsRAGAgent
    participant RC as Response Cache
    participant KB as Milvus Vector DB
    participant LLM as Ollama LLM
    participant MCP as MCP Server (/api/mcp/*)
    participant SK as Skill Registry (retrieval/answer_generation/knowledge_base)

    U->>FE: Send question
    FE->>API: POST /v1/chat/completions (stream=true)

    API->>AG: stream_answer() or stream_answer_web_search_only()

    AG->>RC: semantic cache lookup
    alt Cache hit
        RC-->>AG: cached answer + sources
        AG-->>API: stream cached chunks
    else Cache miss
        AG->>KB: retrieve_context(top_k)
        KB-->>AG: context chunks + sources
        AG->>LLM: generate_stream(prompt)
        LLM-->>AG: answer chunks
        AG-->>API: stream chunks + sources
    end

    API-->>FE: SSE data chunks
    FE-->>U: incremental response render

    Note over MCP,SK: Separate path (tool management/discovery)
    API->>MCP: startup initializes RAGAgentMCPServer
    MCP->>SK: register_tools() for each skill

    Note over FE,MCP: React chat does NOT directly call MCP skill endpoints
    Note over API,MCP: External clients may call /api/mcp/skills and /api/mcp/tools/call
```

## Who Uses Skills and By Whom

- Skills are backend capability groups used by the MCP server to organize tools by category:
  - `retrieval`
  - `answer_generation`
  - `knowledge_base`
- The MCP server registers skills at startup and exposes them through MCP endpoints.
- External MCP/API consumers (developers, agent integrations, automation clients) can:
  - list skills (`GET /api/mcp/skills`)
  - read skill docs (`GET /api/mcp/skills/{skill_name}`)
  - invoke tools (`POST /api/mcp/tools/call`)
- The React chatbot path (`/v1/chat/completions`) primarily uses direct agent methods, not MCP skill endpoints.

## Related Files

- `chatbots/react-chatbot/src/App.js`
- `api_server.py`
- `src/mcp/mcp_server.py`
- `src/tools/tool_registry.py`
- `src/agents/skills/retrieval_skill.py`
- `src/agents/skills/answer_generation_skill.py`
- `src/agents/skills/knowledge_base_skill.py`
