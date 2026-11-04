---
inclusion: auto
name: strands-agents
description: Patterns, APIs, and best practices for implementing, refactoring, debugging, or testing Strands Agents and the 3-node RAG workflow in this project. Also covers MCP tool exposure and when to use AgentCore for serverless deployment.
---

# Strands Agent Development

This project uses real Strands agents (`strands-agents>=1.27.0`) as the core implementation. Do not use LangGraph or other graph frameworks. Do not use AgentCore patterns in the core application — AgentCore is reserved for serverless deployments only.

Always confirm the API surface against `src/agents/strands_graph_agent.py` before copying examples. Do not guess method signatures.

## Architecture: 3-Node Conditional Routing

```
User Query
  → 1. TopicChecker (fast model, no tools)     — validates scope, early exit if out of scope
  → 2. SecurityChecker (fast model, no tools)  — detects malicious queries, early exit if unsafe
  → 3. RAGWorker (powerful model + @tool fns)  — search_knowledge_base(), generate_response()
  → Answer with sources
```

RAGWorker also carries a `BeforeToolCallEvent` hard-guardrail hook
(`SecurityGuardrailHook`, `src/agents/guardrail_hooks.py`) that cancels a tool
call whose input is a security/injection attempt — a framework-level block
independent of the node checks. See `docs/ANTI_HALLUCINATION.md` (Layer 4b).

Routing happens inside the graph. The public entry point `StrandsGraphRAGAgent.answer_question(...)` is async and returns an `(answer, sources)` tuple — not a `RAGResult`.

## Layers

1. Strands Agents (core) — `src/agents/strands_graph_agent.py`. Primary focus.
2. MCP server (interface) — `src/mcp/mcp_server.py`. Wraps the agent to expose tools over MCP; delegates, does not duplicate logic.
3. AgentCore (optional serverless) — only for AWS Lambda + Bedrock deployments. See `docs/DEPLOYMENT.md` and `docs/SERVERLESS_LOCAL.md`. Do not mix with the Strands core.

## Key Patterns

- Use fast models (0.5–1B) for validation nodes; use powerful models (8B+) only for the RAG worker. Early exit on rejection so the expensive model never runs.
- Mark every function passed to an Agent with the Strands `@tool` decorator. Keep tool params and returns typed.
- Validation nodes return a structured `ValidationResult` (`is_valid`, `reason`, `category`) for routing — never raw strings.
- Cache embeddings; never recompute for the same question.
- Keep agents focused and single-responsibility with meaningful names (TopicChecker, SecurityChecker, RAGWorker).

## Testing

- `answer_question` is async and returns `(answer, sources)` — assert against the tuple.
- Test nodes against the `ValidationResult` model, not a `.is_threat` attribute (it does not exist).
- Playwright E2E for the React chatbot lives in `chatbots/react-chatbot/e2e/`. Use `data-testid` selectors, wait for dynamic content, keep tests independent, test happy and error paths.

## References

- Strands samples: https://github.com/aws-samples/sample-strands-agent-with-agentcore
- AgentCore samples: https://github.com/awslabs/amazon-bedrock-agentcore-samples
- Milvus docs: `document_loaders/milvus_docs/en/`
