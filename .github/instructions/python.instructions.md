# Python
- This project uses `uv` for environment and dependency management (see `pyproject.toml` and `.github/workflows/ci.yml`). The virtual environment lives in `.venv`.
- Run tooling through `uv run`: tests with `uv run pytest`, linting with `uv run ruff check --fix`, formatting with `uv run ruff format`, type checking with `uv run mypy .`. Install/sync dependencies with `uv sync --extra dev`.
- Use snake_case as default file name and folder convention
- NEVER remove or modify existing test cases unless explicitly requested
- Keep all validation tests that verify current behavior
- When modifying code, ensure existing tests still pass
- Use type hints for function parameters and return values
- Follow PEP 8 style guidelines for code formatting
- Use f-strings for string formatting instead of .format() or %
- Only use f-string when they're is some values to concatenate
- Handle exceptions explicitly with try/except blocks
- Use list/dict comprehensions when appropriate for readability
- Import modules at the top of files, grouped: standard library, third-party, local
- Use descriptive variable and function names
- Keep functions small and focused on single responsibility
- Use constants for magic numbers and strings
- Add docstrings for classes and public methods
- Use pathlib for file path operations instead of os.path
- Prefer context managers (with statements) for resource handling
- Use unicode for icons
## Type Hints (Missing)
- Function return types: Always required
- Type aliases for complex types:
  ```python
  EmbeddingVector = List[float]
  SearchResults = Dict[str, Any]
