# Strands Agent Development Support

This repository provides a Strands-specific Copilot agent for discussion and troubleshooting, and an on-demand skill for project-aware implementation work.

## Implement or change Strands code

Invoke `/strands-agent-development` with the task you want completed. For example:

```text
/strands-agent-development Add a focused test for the RAG worker's retry behavior
```

The skill directs Copilot to inspect the current implementation, callers, and tests before making changes. It emphasizes reusing project patterns, preserving existing behavior, respecting the `src/` and `document-loaders/` isolation boundary, updating relevant docs, and running focused tests. It is not a code template generator and does not assume every task needs a new agent or the full three-node workflow.

## Discuss design or troubleshoot

Use `@strands-expert` for architecture questions, framework guidance, or help diagnosing an issue:

```text
@strands-expert Should this capability be a Strands tool or an MCP server tool?
```

For code changes, use the skill workflow so recommendations are grounded in current repository code and tests.

## Project references

- Main Strands workflow: `src/agents/strands_graph_agent.py`
- RAG routing: `src/agents/rag_routing.py`
- MCP integration: `src/mcp/mcp_server.py`
- Source isolation requirement: [src-isolation.instructions.md](instructions/src-isolation.instructions.md)
- General project guidance: [copilot-instructions.md](copilot-instructions.md)
