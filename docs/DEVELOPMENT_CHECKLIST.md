# Development Checklist for Core Functionality Changes

## Pre-Development

- [ ] **Create Feature Branch**
  ```bash
  git checkout -b feature/descriptive-name
  ```

- [ ] **Document Expected Behavior**
  - Write down current behavior
  - Define new behavior
  - List affected components
  - Identify potential side effects

## During Development

### 1. Feature Flag Implementation (MANDATORY for Core Changes)

- [ ] Add environment variable to `.env.example`
  ```bash
  # New Feature: Web Search Integration
  ENABLE_WEB_SEARCH=false  # Off by default
  WEB_SEARCH_FALLBACK_ONLY=true  # Only when KB empty
  ```

- [ ] Add setting to `src/config/settings.py`
  ```python
  enable_web_search: bool = Field(
      default=False,
      validation_alias="ENABLE_WEB_SEARCH",
  )
  ```

- [ ] Wrap new code in conditional
  ```python
  if settings.enable_web_search:
      # New functionality
  else:
      # Original behavior (unchanged)
  ```

### 2. Write Tests FIRST (Test-Driven Development)

- [ ] **Regression Test** - Ensure existing behavior still works
  ```python
  def test_existing_behavior_unchanged():
      """Verify original functionality not broken."""
      # Test with feature flag OFF
      result = agent.answer_question("What is Milvus?")
      assert result.answer is not None
      assert len(result.sources) > 0
  ```

- [ ] **New Feature Test** - Test new functionality
  ```python
  def test_new_feature_when_enabled():
      """Verify new feature works when enabled."""
      # Test with feature flag ON
      settings.enable_feature = True
      result = agent.answer_question("What is Milvus?")
      # Assert new behavior
  ```

- [ ] **Edge Cases Test**
  - Empty results
  - Error conditions
  - Timeout scenarios
  - Invalid inputs

### 3. Run Test Suite

```bash
# Must pass BEFORE committing
pytest tests/ -v
pytest --cov=src --cov-report=term-missing

# Check for new errors
pytest tests/ --tb=short
```

- [ ] All existing tests pass
- [ ] New tests pass
- [ ] Code coverage ≥ 80%
- [ ] No new lint errors (`ruff check`)

### 4. Code Quality Tools

Run all quality checks before committing. These tools are also enforced by pre-commit hooks.

#### Python Code Quality

**Ruff - Linter and Formatter**
```bash
# Check for linting errors (imports, complexity, style)
uv run ruff check .

# Auto-fix linting errors
uv run ruff check --fix .

# Format code (100-char line limit)
uv run ruff format .

# Check specific file
uv run ruff check src/agents/strands_graph_agent.py
```

**Mypy - Static Type Checker**
```bash
# Check all files for type errors
uv run mypy .

# Check specific directory
uv run mypy src/

# Show detailed error information
uv run mypy . --show-error-codes

# Common fixes for mypy errors:
# - Add type hints: def func() -> str:
# - Add type ignore: from module import thing  # type: ignore[import-untyped]
# - Fix attribute errors: Use correct attribute name from Settings
```

#### YAML/Configuration Files

**yamllint - YAML Linter**
```bash
# Check all YAML files
yamllint .

# Check specific file
yamllint .github/workflows/ci.yml

# Check with custom config
yamllint -c .yamllint .

# Common YAML issues:
# - Line too long (max 120 chars)
# - Incorrect indentation (use 2 spaces)
# - Missing document start (---)
# - Trailing whitespace
```

Configuration in `.yamllint`:
```yaml
---
extends: default
rules:
  line-length:
    max: 120
    level: warning
    allow-non-breakable-words: true
```

#### Pre-commit Hooks (Automated)

**Run All Checks at Once**
```bash
# Run all pre-commit hooks manually
pre-commit run --all-files

# Run on staged files only (fastest)
pre-commit run

# Skip hooks (NOT recommended)
git commit --no-verify
```

**Pre-commit Hook Order:**
1. ✅ Trailing whitespace fixer
2. ✅ End-of-file fixer
3. ✅ Large file checker (>500KB)
4. ✅ Merge conflict detector
5. ✅ YAML syntax checker
6. ✅ yamllint (YAML style)
7. ✅ Ruff linter (auto-fix)
8. ✅ Ruff formatter
9. ✅ Mypy (type checking)
10. ✅ Pytest (test suite)

**Install Pre-commit Hooks**
```bash
# First-time setup
pre-commit install

# Update hooks to latest versions
pre-commit autoupdate
```

#### Quality Checklist

Before committing, ensure:
- [ ] `ruff check --fix .` (no errors)
- [ ] `ruff format .` (code formatted)
- [ ] `mypy .` (no type errors)
- [ ] `yamllint .` (YAML files valid)
- [ ] `pytest --cov` (tests pass, coverage ≥ 80%)
- [ ] `pre-commit run --all-files` (all hooks pass)

**Common Error Fixes:**

| Error | Fix |
|-------|-----|
| `mypy: Cannot find implementation` | Fix import path (check module exists) |
| `mypy: "Settings" has no attribute` | Use correct attribute name (check `settings.py`) |
| `mypy: module is installed, but missing library stubs` | Add `# type: ignore[import-untyped]` |
| `ruff: Line too long` | Break line or let `ruff format` auto-fix |
| `yamllint: line too long` | Break YAML line with proper indentation |
| `trailing-whitespace` | Remove spaces at end of lines (auto-fixed) |
| `end-of-file-fixer` | Add newline at end of file (auto-fixed) |

### 5. Manual Testing Checklist

Test with feature flag **OFF**:
- [ ] Health endpoint responds
- [ ] Question answering works
- [ ] Cache lookup works
- [ ] Sources returned correctly
- [ ] Response time < 5s

Test with feature flag **ON**:
- [ ] New feature activates
- [ ] Graceful degradation if feature fails
- [ ] No errors in logs
- [ ] Performance acceptable

### 6. Code Review Requirements

**For Core Functions** (`answer_question`, `rag_worker_node`, `retrieve_context`):
- [ ] Self-review checklist completed
- [ ] Breaking changes documented
- [ ] Rollback plan documented
- [ ] Performance impact measured
- [ ] Backward compatible

**Review Questions:**
- Does this change existing behavior without a feature flag?
- Can we roll back by toggling a flag (no code change)?
- Are there tests for both ON and OFF states?
- Is the cache invalidation strategy clear?
- What happens if the new feature fails?

## Pre-Deployment

### 7. Documentation Updates

- [ ] Update `CHANGELOG.md`
  ```markdown
  ## [Unreleased]
  ### Added
  - Web search integration (disabled by default, enable with ENABLE_WEB_SEARCH=true)
  ```

- [ ] Update `.env.example` with new variables
- [ ] Update `docs/GETTING_STARTED.md` if config changes
- [ ] Update `docs/DEVELOPMENT.md` with usage examples

### 8. Deployment Plan

- [ ] **Gradual Rollout Strategy**
  - Phase 1: Feature flag OFF (default)
  - Phase 2: Enable for 1% of traffic (canary)
  - Phase 3: Enable for 10% (A/B test)
  - Phase 4: Full rollout if metrics good

- [ ] **Rollback Plan**
  ```bash
  # Option 1: Toggle flag (instant)
  echo "ENABLE_NEW_FEATURE=false" >> .env
  # Restart: kill -HUP $(cat api_server.pid)

  # Option 2: Git revert
  git revert HEAD
  git push

  # Option 3: Restore backup
  cp backup/file.py src/agents/file.py
  ```

- [ ] **Monitoring Plan**
  - Error rate threshold: < 1%
  - Response time threshold: < 5s p95
  - Cache hit rate: > 30%
  - Hallucination reports: monitor for 48h

### 9. Post-Deployment

- [ ] Monitor error logs for 1 hour
- [ ] Check performance metrics (response time, cache hit rate)
- [ ] Test 5 common queries manually
- [ ] Verify cache warmup completed
- [ ] Check for user reports/feedback

**Red Flags - Immediate Rollback:**
- Error rate > 5%
- Response time > 10s
- Cache failures
- Hallucination increase
- Breaking existing functionality

## Core Functions Requiring Extra Scrutiny

These functions need **2+ reviewer approval** + **full test coverage**:

1. `answer_question()` - Main query entry point
2. `rag_worker_node()` - RAG pipeline core
3. `retrieve_context()` - Vector search
4. `search_cache()` - Cache lookup
5. `store_response()` - Cache storage
6. Any function in `strands_graph_agent.py`

## Quick Reference Commands

```bash
# Create feature branch
git checkout -b feature/name

# Run tests
pytest tests/ -v --cov

# Code quality checks
ruff check --fix        # Lint and auto-fix
ruff format .           # Format code
mypy .                  # Type checking
yamllint .              # YAML validation
pre-commit run --all-files  # All quality checks

# Test with feature ON
ENABLE_FEATURE=true python api_server.py

# Test with feature OFF (default)
python api_server.py

# Rollback via git
git revert HEAD && git push

# Rollback via flag
echo "ENABLE_FEATURE=false" >> .env && systemctl restart api-server
```

## Lessons Learned

### ❌ What NOT to Do

1. **Don't modify core functions without feature flags**
   - Always use flags for new features in production code

2. **Don't skip testing**
   - Write tests BEFORE implementing
   - Test both old and new behavior

3. **Don't deploy directly to main**
   - Use feature branches
   - Require code review

4. **Don't assume backward compatibility**
   - Test with existing data/queries
   - Verify cache doesn't break

### ✅ What TO Do

1. **Use feature flags** for all new features
2. **Write tests first** (TDD approach)
3. **Document rollback plan** before deploying
4. **Monitor metrics** for 24-48h after deploy
5. **Keep changes small** and focused
6. **Test with real data** before merging

## Emergency Rollback Contacts

If you need to revert a change:
1. Check this document for rollback commands
2. Toggle feature flag if available
3. Git revert if needed
4. Document what went wrong in `docs/INCIDENTS.md`
