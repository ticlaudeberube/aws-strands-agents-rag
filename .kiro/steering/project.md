# Project Context

AWS Strands Agents RAG system. Uses Milvus for vector storage and implements a Retrieval Augmented Generation pipeline with real `strands.Agent` instances.

## Code Structure

- `src/agents/` — Strands agent implementations (graph agent, RAG routing)
- `src/tools/` — Reusable tools including the `MilvusVectorDB` wrapper
- `src/config/` — Configuration (`settings.py`, pydantic-settings)
- `src/mcp/` — Model Context Protocol server exposing agent tools
- `document_loaders/` — Standalone document loading and embedding utilities
- `chatbots/` — CLI chatbot and React web UI (`react-chatbot/`, with Playwright E2E in `e2e/`)
- `tests/` — Unit and integration tests (pytest)
- `docs/` — Developer documentation (see `docs/INDEX.md`)
- `infrastructure/terraform/` — Serverless/AWS deployment

## Architecture Isolation (critical)

`src/` must NEVER import from `document_loaders/`, and `document_loaders/` must NEVER import from `src/`. They are independent packages with their own settings; duplicated logic between them is intentional, not a DRY violation.

## Feature Development

- Do not implement new features without first asking for approval.
- Update documentation in the same change as the code.
- Solve the task that was asked; avoid unrequested refactors.

## Helpful Commands

- Load docs into Milvus: `uv run python document_loaders/load_milvus_docs_ollama.py`
- Interactive chat: `uv run python chatbots/interactive_chat.py`
- API server: `uv run python api_server.py`
- Tests: `uv run pytest` (coverage: `uv run pytest --cov`)
- Lint/format/types: `uv run ruff check --fix`, `uv run ruff format`, `uv run mypy .`

## Canonical Documentation Map

| Topic | File |
|-------|------|
| Setup, install, environment | `docs/GETTING_STARTED.md` |
| How-to, code examples | `docs/HOW_TO.md` |
| Architecture, runtime flow | `docs/ARCHITECTURE.md` |
| REST API, endpoints | `docs/API_SERVER.md` |
| Anti-hallucination design | `docs/ANTI_HALLUCINATION.md` |
| Local MLflow evaluation | `docs/EVAL_LOCAL.md` |
| Serverless/AWS deployment | `docs/DEPLOYMENT.md` |
| Serverless local emulation | `docs/SERVERLESS_LOCAL.md` |
| Chatbot UI behavior | `docs/CHATBOT_GUI_FEATURES.md` |
| Docker | `docker/README.md` |
| Testing | `tests/README.md` |
