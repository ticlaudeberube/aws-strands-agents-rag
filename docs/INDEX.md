# Documentation Index

This is the current, active documentation set for the project.

## Start here

- [README.md](../README.md) — project overview and quick links
- [HOW_TO.md](HOW_TO.md) — practical setup and usage guide
- [GETTING_STARTED.md](GETTING_STARTED.md) — installation and environment setup
- [ARCHITECTURE.md](ARCHITECTURE.md) — mode selection and runtime flow
- [API_SERVER.md](API_SERVER.md) — API contract and sample requests
- [CHATBOT_GUI_FEATURES.md](CHATBOT_GUI_FEATURES.md) — chatbot UI behavior and feature reference

## Quality and evaluation

- [ANTI_HALLUCINATION.md](ANTI_HALLUCINATION.md) — layered anti-hallucination design, thresholds, and observability
- [EVAL_LOCAL.md](EVAL_LOCAL.md) — local MLflow evaluation harness (usage and interpretation)
- [ROADMAP.md](ROADMAP.md) — follow-up work for Guardrails, PII handling, and token-aware chunking

## Deployment

- [DEPLOYMENT.md](DEPLOYMENT.md) — serverless/AWS deployment overview
- [SERVERLESS_LOCAL.md](SERVERLESS_LOCAL.md) — run serverless mode locally (real Bedrock + local OpenSearch/Redis)
- [AWS_DEPLOYMENT_GAPS.md](AWS_DEPLOYMENT_GAPS.md) — what stands between local serverless and a real AWS deploy

## Interfaces and tooling

- MCP server: the `/api/mcp/*` REST surface (see [API_SERVER.md](API_SERVER.md)) exposes the agent's tools (`src/mcp/mcp_server.py`)
- Document ingestion (corpus seed): `uv run python document_loaders/load_docs_opensearch.py` (see [HOW_TO.md](HOW_TO.md))
- Document ingestion (local OpenSearch): `uv run python scripts/ingest_local_opensearch.py` (see [GETTING_STARTED.md](GETTING_STARTED.md))
- Playwright E2E agents: three Kiro agents in `.kiro/agents/` (see [tests/README.md](../tests/README.md))

## Quick decisions

- Local development: use `DEPLOYMENT_MODE=local`
- AWS deployment: use `DEPLOYMENT_MODE=serverless`
- Need runtime behavior details: read [API_SERVER.md](API_SERVER.md)
- Need architecture context: read [ARCHITECTURE.md](ARCHITECTURE.md)

## Notes

This index intentionally excludes historical or implementation-archive documents that no longer reflect the current code or configuration.
