#!/bin/bash
# Wrapper script to clear RAG Agent caches

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Clearing RAG Agent caches..."
python "$PROJECT_ROOT/scripts/clear_cache.py"
