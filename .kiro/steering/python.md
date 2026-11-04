---
inclusion: fileMatch
fileMatchPattern: '*.py'
---

# Python Conventions

- Environment and dependencies managed with `uv` (see `pyproject.toml`). The venv lives in `.venv`. Sync with `uv sync --extra dev`.
- Run all tooling through `uv run`: `uv run pytest`, `uv run ruff check --fix`, `uv run ruff format`, `uv run mypy .`.
- snake_case for files and directories.
- NEVER remove or modify existing test cases unless explicitly requested. Keep tests that verify current behavior; ensure existing tests still pass after changes.
- Type hints required on all function parameters and return values. Use `X | Y` for unions and type aliases for complex types.
- Follow PEP 8. Use f-strings only when interpolating values.
- Handle exceptions explicitly with typed `except` clauses — no bare `except`.
- Imports at top of file, grouped: standard library, third-party, local. Ruff sorts with `--fix`. No wildcard imports.
- Keep functions small and single-responsibility. Descriptive names. Constants for magic values. Docstrings on classes and public methods.
- Use `pathlib` for paths and context managers for resources.

## Error Handling & Logging

- Use typed exceptions from `src/config/settings.py` or custom exception classes.
- Log with context (error type, source, recovery action). Never log secrets, API keys, or embeddings.
- Log levels: DEBUG (dev), INFO (state changes), WARNING (issues), ERROR (failures).

## Testing

- Unit tests fast and mocked; mark integration with `@pytest.mark.integration`, async with `@pytest.mark.asyncio`, slow (>1s) with `@pytest.mark.slow`.
- Follow Arrange-Act-Assert. Target 80% statement coverage.
