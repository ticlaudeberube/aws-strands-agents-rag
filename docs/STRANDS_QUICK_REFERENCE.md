# Quick Reference: Strands Agent Architecture

## Architecture Overview

The system uses a Strands-compliant architecture with proper tool organization and MCP protocol support:

| Component | Details |
|-----------|---------|
| **Agent Base** | Graph-based `StrandsGraphRAGAgent` (3-node: Topic Check → Security Check → RAG Worker) |
| **Tool Definition** | Methods with full docstrings and type hints |
| **Tool Management** | Centralized ToolRegistry with skill-based organization |
| **Protocol** | Model Context Protocol (MCP) for standard tool communication |
| **Tools** | 6 tools organized into 3 skills |
| **Inference** | Ollama LLM (qwen2.5:0.5b) for fast local inference |
| **Vectors** | Milvus for semantic search and storage |

---

## For Developers: Quick Start

### 1. Using StrandsGraphRAGAgent

**Standard usage:**
```python
from src.agents.strands_graph_agent import StrandsGraphRAGAgent

agent = StrandsGraphRAGAgent(settings)

# Full RAG pipeline
answer = agent.answer_question(
    question="What is Milvus?",
    collection="milvus_docs"
)

# Or call tools directly for more control
docs = agent.retrieve_documents(
    collection="milvus_docs",
    query="collection creation",
    top_k=5
)

answer = agent.generate_answer(
    question="What is Milvus?",
    context=docs[0]
)

# StrandsGraphRAGAgent doesn't require explicit close
if hasattr(agent, 'close'):
    agent.close()
```

### 2. Adding a New Tool

**Old approach:**
```python
class RAGAgent:
    def my_new_tool(self, param1):
        # tool code
        pass
```

**New approach (Strands-compliant):**

1. Add to your skill file
2. Decorate with `@tool`
3. Register in skill class

```python
# src/agents/skills/my_skill.py

from strands.agents import tool

class MySkill:
    @staticmethod
    def register_tools(registry, agent):
        registry.register_tool(
            ToolDefinition(
                name="my_new_tool",
                description="What it does",
                function=agent.my_new_tool,
                parameters={...},
                skill_category="my_category",
            )
        )

# In StrandsRAGAgent
@tool
def my_new_tool(self, param1: str) -> str:
    """Tool description shown to agent and users.

    Args:
        param1: Parameter description

    Returns:
        Result description
    """
    # Implementation
    return result
```

### 3. Understanding Tool Organization (Skills)

Tools are grouped by purpose:

```
retrieval_skill/           # Search and retrieve documents
├── retrieve_documents()
├── search_by_source()
└── list_collections()

answer_generation_skill/   # Generate answers from context
├── generate_answer()
└── summarize_context()

knowledge_base_skill/      # Manage documents
├── add_documents()
├── delete_collection()
└── update_collection()
```

**Benefit:** Agent loads full tool docs only when activating relevant skill (token efficient).

### 4. Testing a Tool

```python
import asyncio
from src.config import Settings
from src.agents import StrandsRAGAgent

async def test_tool():
    settings = Settings()
    agent = StrandsRAGAgent(settings)

    # Call tool directly
    result = await agent.retrieve_documents(
        collection_name="test_collection",
        query="test query"
    )

    print(result)

asyncio.run(test_tool())
```

### 5. Debugging with Strands

**Enable detailed logging:**
```python
import logging

logging.basicConfig(level=logging.DEBUG)

# Strands logs each tool call, reasoning, and decision
```

**With observability (future):**
```python
# After Phase 2 implementation
agent_trace = await agent.get_trace_for_last_call()
print(agent_trace)  # Full execution trace with times
```

---

## Common Tasks

### Q: How do I add a new tool?
**A:**
1. Add method to `StrandsRAGAgent` with `@tool` decorator
2. Create/update skill class in `src/agents/skills/`
3. Register tool in skill's `register_tools()` method
4. Test with `test_strands_agent.py`

### Q: How do I modify existing tool behavior?
**A:**
1. Update the tool method in `StrandsRAGAgent`
2. Update docstring if parameters change
3. Update tool definition in skill registration
4. Tests should still pass (if not, update them)

### Q: How do I check what tools are available?
**A:**
```python
from src.tools.tool_registry import get_registry

registry = get_registry()
print(registry.list_tools())        # All tools
print(registry.list_skills())       # Skills and tool counts
print(registry.get_tools_by_skill("retrieval"))  # Tools in a skill
```

### Q: How do I call the agent and see the reasoning?
**A:**
```python
# Basic call (agent picks tools)
result = await agent("What is Milvus?")

# With trace (after observability integration)
trace = await agent.get_last_trace()
for step in trace.steps:
    print(f"{step.tool}: {step.input} -> {step.output}")
```

### Q: How is this different from LangChain/CrewAI?
**A:**
- **Strands**: Framework-agnostic, designed for AWS integration
- **LangChain**: Graph-based, good for simple chains
- **CrewAI**: Specialized for role-based agents
- **Bedrock AgentCore**: AWS-native, handles production infrastructure

This project uses Strands for modularity and AgentCore for scale.

### Q: How do I use StrandsGraphRAGAgent?
**A:** Import and instantiate:
```python
from src.agents.strands_graph_agent import StrandsGraphRAGAgent

agent = StrandsGraphRAGAgent(settings)
answer = agent.answer_question(
    question="What is Milvus?",
    collection="milvus_docs"
)
```

Or use MCP endpoints via HTTP:
```bash
curl -X POST http://localhost:8000/api/mcp/tools/call \
  -d '{"tool": "retrieve_documents", "arguments": {...}}'
```

---

## Architecture Diagram: How It Works Now

```
User Request
    │
    ▼
API Server (FastAPI)
    │
    ▼
Strands Agent (orchestrator)
    │
    ├─────────────────────────────┐
    │                             │
    ▼                             ▼
[Question Analysis]        [Tool Registry]
    │                             │
    │ "What tools needed?"        │ "Available tools:"
    │                             ├─ retrieval
    ▼                             ├─ generation
[Tool Selection]                  ├─ kb_management
    │                             └─ search
    │
    ├──────────────────────────┐
    │                          │
    ▼                          ▼
retrieve_documents     generate_answer
    │                          │
    ├─────────────┬────────────┤
    │             │            │
    ▼             ▼            ▼
[Ollama]    [Milvus]    [Context]
(Embeddings) (Search)    (Synthesis)
    │             │            │
    └─────────────┴────────────┘
                  │
                  ▼
            [LLM Response]
                  │
                  ▼
            [Format & Return]
```

### Tool Activation Flow

```
User: "What is Milvus?"
│
├─ [Scope Check] → In scope? ✓
├─ [Retrieval Skill] → Load SKILL.md documentation
│  └─ Now knows about: retrieve_documents, search_by_source, list_collections
├─ [Tool Selection] → Picks retrieve_documents
│  │  Params: collection="milvus_docs", query="What is Milvus?", top_k=5
│  └─ Executes → Returns 5 relevant docs
├─ [Answer Gen Skill] → Load answer generation docs
│  └─ Now knows about: generate_answer, summarize_context
├─ [Tool Selection] → Picks generate_answer
│  │  Params: question="...", context="..."
│  └─ Executes → Returns synthesized answer
└─ [Return] → Final answer to user
```

---

## Performance Expectations

### Latency
- **Tool call**: 50-200ms (Milvus search: 50-100ms, LLM: 100-300ms)
- **Full RAG**: 200-500ms (retrieval + generation)
- **Strands overhead**: <50ms (reasoning loop, tool selection)

### Token Usage
- **Before optimization**: Sends all 100+ tools to model ❌
- **After skills**: Sends ~3 tools initially + skill docs on demand ✅
- **With prompt caching**: Reuses tool docs across calls ✅

### Memory
- **RAM**: ~500MB base (Strands SDK + agent instance)
- **Cache**: Configurable (default: 10MB for LRU cache)
- **After AgentCore Memory**: Persistent, but external

---

## Troubleshooting

### Issue: "Tool not found" error
**Solution:**
1. Check tool is registered in skill's `register_tools()`
2. Verify skill is registered in API startup
3. Check spelling matches `@tool` function name

### Issue: Tool parameters don't match
**Solution:**
1. Update tool definition in skill class `parameters` dict
2. Ensure Strands agent docstring matches
3. Test individually: `await agent.tool_name(...)`

### Issue: Agent not calling expected tools
**Solution:**
1. Check agent can see the skill (list_tools())
2. Check tool description is clear
3. Make sure tool is relevant to the question
4. Review agent reasoning (after observability added)

### Issue: Performance degraded
**Solution:**
1. Check Milvus is running: `milvus health`
2. Check Ollama is responsive: `ollama list`
3. Profile with observability traces
4. Check cache hit rates
5. Verify top_k parameter isn't too large

---

## Migration Timeline Estimate

| Phase | Tasks | Timeline | Risk |
|-------|-------|----------|------|
| 1 | Strands integration, tool decorators, registry | 1-2 weeks | Low |
| 2 | MCP server, skill system | 2 weeks | Low |
| 3 | AgentCore integration, memory | 2-3 weeks | Medium |
| 4 | Observability, tracing | 1-2 weeks | Low |
| 5 | Multi-agent (A2A), optimization | 2-3 weeks | Medium |
| **Total** | | 8-10 weeks | |

**Recommendation**:
- Start Phase 1 immediately (foundational)
- Run Phase 1-2 in parallel with production (backward compatible)
- Deploy Phase 3+ after Phase 1-2 are stable

---

## Useful Links

- [Strands Agents Documentation](https://strandsagents.com/latest/documentation/)
- [AWS AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
- [Strands + AgentCore Example](https://github.com/aws-samples/sample-strands-agent-with-agentcore)
- [MCP Protocol Spec](https://modelcontextprotocol.io/)
- [Tool Design Best Practices](https://medium.com/towards-artificial-intelligence/agent-skills-part-2-bridging-skills-with-production-tool-ecosystems-422e4a63fcad)

---

## Support

For implementation questions:
1. Check [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for detailed steps
2. Review reference implementations
3. Check [ARCHITECTURE_EVALUATION.md](ARCHITECTURE_EVALUATION.md) for context
4. Consult Strands documentation for SDK-specific questions
