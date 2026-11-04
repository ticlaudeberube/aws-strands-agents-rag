# Source Isolation

The project maintains strict, intentional separation between two independent packages:

- `src/` — production application (agents, tools, config, mcp). Minimal dependencies.
- `document_loaders/` — standalone data pipeline utility (ingestion, embedding, indexing). Deployable independently.

## Rules

1. `src/` MUST NOT import from `document_loaders/`. Duplicate the implementation in `src/` instead (e.g. `src/tools/milvus_client.py`).
2. `document_loaders/` MUST NOT import from `src/`. Use `document_loaders/local_settings.py` instead.
3. Duplicated logic between the two packages is intentional and correct — not a DRY violation. Each serves a different purpose and can evolve independently.
4. Each package owns its configuration: `src/config/settings.py` vs `document_loaders/local_settings.py`. They can differ (e.g. different default models).

## Placing new code

- Production feature (agent logic, agent tools, API, prod config) → `src/`, with no loader imports.
- Data loading feature (ingestion scripts, document processing, embedding/indexing) → `document_loaders/`, with no `src` imports.

## Verifying isolation

```bash
grep -r "from src" document_loaders/     # expect no matches
grep -r "import src" document_loaders/   # expect no matches
```

Keep dependencies one-way only — circular imports break both packages.
