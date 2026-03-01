#!/bin/bash
# Setup pre-commit hooks for automated code formatting and linting

set -e

echo "Installing pre-commit package..."
pip install pre-commit

echo "Installing pre-commit hooks..."
pre-commit install

echo "Running pre-commit on all files..."
pre-commit run --all-files

echo "✅ Pre-commit hooks setup complete!"
echo ""
echo "ℹ️  The following hooks will run automatically on git commit:"
echo "  - black: Auto-format Python code"
echo "  - ruff: Lint and fix code issues"
echo ""
echo "To manually run the hooks on all files:"
echo "  pre-commit run --all-files"
echo ""
echo "To skip pre-commit hooks on a commit (not recommended):"
echo "  git commit --no-verify"
