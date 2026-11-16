# Scripts

Helper scripts for running, seeding, and operating the RAG system. Run them
through `uv` from the project root, e.g. `uv run python scripts/check_setup.py`.

## Setup & diagnostics

| Script | Purpose |
|--------|---------|
| `check_setup.py` | Verify Ollama and the local OpenSearch connection; prints the KB index in use. Run before ingesting or starting the server. |
| `ERROR_SCENARIOS.py` | Prints a recovery guide for common Ollama/OpenSearch failures. |
| `setup.sh` / `setup.bat` | One-time local environment setup (dependencies, next-step hints). |
| `setup-precommit.sh` | Install the pre-commit hooks. |

## Ingestion

| Script | Purpose |
|--------|---------|
| `ingest_local_opensearch.py` | Chunk + embed (Ollama) + index documents into the local OpenSearch `rag-kb` index. Supports a demo seed and an arbitrary `--docs <dir>` directory. |
| `ingest_serverless_opensearch.py` | Chunk + embed (Bedrock Titan + projection) + index documents into the OpenSearch Serverless `rag-kb` index. Refuses any endpoint that is not an `*.aoss.amazonaws.com` host. Uses the same embedding space as the Lambda. See [VECTORIZATION.md](../docs/VECTORIZATION.md#21a-serverless-direct-script-scriptsingest_serverless_opensearchpy). |

See also the standalone corpus loader
`document_loaders/load_docs_opensearch.py` (seeds the `milvus_docs` knowledge-base
corpus) — it is source-isolated from `src/` and has its own settings.

## Serverless (local emulation)

| Script | Purpose |
|--------|---------|
| `run_serverless_local.py` | Run the serverless code path locally (real Bedrock + local OpenSearch/Redis/DynamoDB). Holds the shared local-backend client builders. |
| `serverless_api_server.py` | Serve the GUI against the serverless shim with a serverless-aware `/health`. |
| `run_lambda_handler_local.py` | Invoke the real Lambda handler end-to-end with local backends. |

See [docs/SERVERLESS_LOCAL.md](../docs/SERVERLESS_LOCAL.md) for the full workflow.

## Evaluation

| Script | Purpose |
|--------|---------|
| `eval_local.py` | Run the tagged question set through Local Mode and log anti-hallucination signals to MLflow. Supports `--sweep-ef` for an HNSW recall sweep. See [docs/EVAL_LOCAL.md](../docs/EVAL_LOCAL.md). |
| `eval_scope.py` | Score the scope gate on `eval/scope_labels.jsonl` (or `--labels`): keyword, embedding, or LLM classifiers, with threshold sweeps. |
| `eval_followup.py` | Measure KB retrieval for follow-up questions on `eval/followup_pairs.jsonl`, comparing raw, last-turn, and recent-turns (`--join-turns`, default `FOLLOWUP_USER_TURNS`) queries. Supports `--json`. See [docs/EVAL_LOCAL.md](../docs/EVAL_LOCAL.md). |

## Operations

| Script | Purpose |
|--------|---------|
| `cache/clear_cache.py` (`clear_cache.sh`) | Delete all documents from the OpenSearch `rag-cache` (Layer 4 semantic cache). |
| `safe_stop.py` (`safe_stop.sh`) | Stop the local stack / API server cleanly, releasing the port. |
| `data/generate_responses_from_api.py` | Query the API for `config/common_questions.json` and write `data/responses.json` for cache pre-loading. |
