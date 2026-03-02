# GitHub Actions Setup for Pre-commit Pipeline

This document describes how to integrate pre-commit checks into your GitHub repository using GitHub Actions.

## Overview

Pre-commit can be enforced at the repository level using GitHub Actions workflows. This ensures all code meeting the `main` branch passes the project's code quality standards automatically.

## Current Local Implementation

Your project includes a local pre-commit configuration (`.pre-commit-config.yaml`) that runs:
- **ruff** - Linting with auto-fixes
- **ruff-format** - Code formatting
- **mypy** - Type checking
- **pytest** - Unit tests

This provides fast feedback to developers during development.

## GitHub Actions Implementation

### Benefits

- ✅ **Enforced centrally** - Cannot be bypassed
- ✅ **Automatic** - Runs on every PR and push
- ✅ **Transparent** - Results visible to all contributors
- ✅ **Blocks merging** - Prevents bad code from reaching main (with branch protection)
- ✅ **Mandatory for all** - Works even for first-time contributors

### Steps to Implement

#### 1. Create Workflow File

Create `.github/workflows/pre-commit.yml`:

```yaml
name: Pre-commit Checks

on:
  pull_request:
  push:
    branches: [main]

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"

      - name: Run pre-commit
        run: pre-commit run --all-files
```

#### 2. Configure Branch Protection

1. Go to repository **Settings**
2. Navigate to **Branches**
3. Add branch protection rule for `main`:
   - Enable "Require a pull request before merging"
   - Enable "Require status checks to pass before merging"
   - Select `pre-commit` workflow as required check
   - Enable "Require branches to be up to date before merging"

#### 3. Update CODEOWNERS (Optional)

Create `.github/CODEOWNERS` to specify code review requirements:

```
# All files require review
* @ticlaudeberube

# Agent-specific
src/agents/ @ticlaudeberube
src/tools/ @ticlaudeberube

# Document loaders
document_loaders/ @ticlaudeberube
```

## Workflow Execution

### When Workflow Runs

- On every push to any branch
- On every pull request to `main`
- Automatically checks code before merge

### What Gets Checked

1. **ruff** - Linting (auto-fixes violations)
2. **ruff-format** - Code formatting (auto-formats)
3. **mypy** - Type checking (reports type errors)
4. **pytest** - Runs all tests with coverage

### Failure Scenarios

If any check fails:
1. Workflow shows as "Failed" on PR
2. Merge button is disabled (with branch protection)
3. Developer must:
   - Run `pre-commit run --all-files` locally
   - Fix any remaining issues
   - Commit and push fixes
   - Re-run workflow automatically

## Local Development Workflow

### Setup (Once)

```bash
# Install pre-commit
pip install pre-commit

# Install git hooks
pre-commit install
```

### Before Committing

```bash
# Manually run pre-commit (optional - runs on commit)
pre-commit run --all-files

# Or just commit normally (hooks run automatically)
git commit -m "Your message"
```

### Troubleshooting

**Bypass checks temporarily (not recommended):**
```bash
git commit --no-verify
```

**Update hook versions:**
```bash
pre-commit autoupdate
```

**Clear cache:**
```bash
pre-commit clean
```

## Comparison: Local vs GitHub Actions

| Aspect | Local | GitHub Actions |
|--------|-------|----------------|
| **Where** | Developer's machine | GitHub servers |
| **When** | Before commit | Every push/PR |
| **Enforcement** | Optional | Mandatory |
| **Bypass** | `--no-verify` | Requires admin |
| **Speed** | Instant | 1-5 minutes |
| **Requirement** | Must install locally | Automatic |
| **Coverage** | Only if developer has it | All code to main |

## Implementation Checklist

- [ ] Create `.github/workflows/pre-commit.yml`
- [ ] Test workflow on a branch
- [ ] Configure branch protection for `main`
- [ ] Update CODEOWNERS (optional)
- [ ] Test with a PR to ensure workflow runs
- [ ] Document in team wiki/onboarding
- [ ] Train team on local setup

## Cost Considerations

GitHub Actions provides free minutes with limitations:
- **Public repos**: Unlimited
- **Private repos**: 2,000 free minutes/month per account

Pre-commit workflow typically uses <1 minute per run, so most projects stay within free tier.

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Pre-commit Documentation](https://pre-commit.com/)
- [Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
