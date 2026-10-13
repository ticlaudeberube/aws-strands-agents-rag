---
name: strands-agent-development
description: "Use when implementing, refactoring, debugging, or testing Strands Agents or AWS Bedrock AgentCore code in this repository, including agent orchestration, @tool functions, RAG integration, and MCP exposure."
argument-hint: "Describe the Strands Agent or AgentCore change you need"
---

# Strands Agent Development

Make project-specific changes to Strands Agent and AgentCore code. Do not generate generic boilerplate or assume a requested change needs a new agent or the full three-node workflow.

## Workflow

1. Clarify the requested behavior from the task. For implementation work, inspect the relevant source files, their callers, and focused tests before proposing a design.
2. Treat the existing implementation as the source of truth. Start with `src/agents/strands_graph_agent.py` for the main Strands workflow, `src/agents/rag_routing.py` for RAG routing, `src/tools/` for reusable tools, and `src/mcp/mcp_server.py` for the MCP integration. Read the relevant settings and tests too.
3. Reuse the narrowest existing helper or pattern that satisfies the request. Preserve public interfaces, routing decisions, error behavior, logging, and configuration unless the task explicitly calls for changing them.
4. Follow the repository's architecture boundaries: `src/` must not import from `document-loaders/`, and `document-loaders/` must not import from `src/`. Keep production agent logic in `src/`; keep ingestion utilities independent.
5. Use the installed Strands APIs and patterns verified in the repository. In particular, inspect current imports and usages of `Agent` and `@tool` rather than copying stale examples or guessing method signatures. Keep tool parameters and return values typed and validate inputs at the appropriate boundary.
6. Keep the main Strands implementation separate from AWS deployment concerns. Use AgentCore patterns only for code that is explicitly part of the serverless AgentCore deployment; do not replace the local/container Strands application with a different orchestration framework.
7. Make the smallest complete change, update directly related tests and canonical documentation, then run the focused pytest tests. Run relevant linting or type checking when the change affects those checks.
8. Report what changed, the behavior preserved or intentionally changed, and the exact validation run and result. If implementation is not requested, answer the question without editing files.

## Project references

- Main implementation: `src/agents/strands_graph_agent.py`
- Routing: `src/agents/rag_routing.py`
- MCP exposure: `src/mcp/mcp_server.py`
- Agent and tool implementations: `src/agents/` and `src/tools/`
- Project guidance: `.github/copilot-instructions.md`
- Architecture and setup documentation: `docs/ARCHITECTURE.md` and `docs/GETTING_STARTED.md`
- Source isolation rule: `.github/instructions/src-isolation.instructions.md`
