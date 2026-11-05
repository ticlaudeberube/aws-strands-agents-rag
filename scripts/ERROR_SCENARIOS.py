"""
ERROR HANDLING & RECOVERY GUIDE
What Happens When Services Don't Respond
========================================

This reference describes what happens when the local backends (OpenSearch or
Ollama) are not available during ingestion or while running the API server, and
how to recover. Run it with ``python scripts/ERROR_SCENARIOS.py`` to print the
guide.

Local Mode backends:
  - Ollama       — LLM + embeddings, http://localhost:11434 (runs on the host)
  - OpenSearch   — vector store + Layer 4 cache, http://localhost:9200
                   (container ``agentcore-rag-opensearch``)
"""

# =============================================================================
# SCENARIO 1: OPENSEARCH IS NOT RUNNING
# =============================================================================

print(
    """
SCENARIO 1: OpenSearch is Not Running
=====================================

WHAT HAPPENS:
1. When you run: python scripts/ingest_local_opensearch.py --docs ./data/docs

ERROR MESSAGE:
  ❌ OpenSearch connection failed at localhost:9200.
     Make sure the local OpenSearch container is running.

RECOVERY STEPS:
1. Check if OpenSearch is running:
   cd docker && docker compose ps
2. If not running, start it:
   cd docker && docker compose up -d opensearch
3. Wait ~30-60 seconds for the cluster to be ready:
   curl -s http://localhost:9200/_cluster/health
4. Try again:
   python scripts/ingest_local_opensearch.py --docs ./data/docs
"""
)

# =============================================================================
# SCENARIO 2: OPENSEARCH IS STARTING BUT SLOW
# =============================================================================

print(
    """
SCENARIO 2: OpenSearch is Starting but Slow
===========================================

WHAT HAPPENS:
1. OpenSearch is running but the cluster is not yet green/yellow
2. Index creation or search requests time out

RECOVERY STEPS:
1. Watch the container come up:
   docker compose -f docker/docker-compose.yml logs -f opensearch
2. Poll cluster health until it is yellow or green:
   curl -s http://localhost:9200/_cluster/health
3. Once ready, re-run your command.
"""
)

# =============================================================================
# SCENARIO 3: OLLAMA IS NOT RUNNING
# =============================================================================

print(
    """
SCENARIO 3: Ollama is Not Running
==================================

ERROR MESSAGE:
  🔍 Checking Ollama...
    ❌ Cannot connect to Ollama at http://localhost:11434
       Make sure Ollama is running:
       - Run: ollama serve
       - Or on macOS: open the Ollama app from Applications

RECOVERY STEPS:
1. Start Ollama (in a separate terminal):
   ollama serve
2. Re-run your command.
"""
)

# =============================================================================
# SCENARIO 4: EMBEDDING MODEL NOT AVAILABLE
# =============================================================================

print(
    """
SCENARIO 4: Embedding Model Not Available
===========================================

ERROR MESSAGE:
    ❌ Embedding model 'nomic-embed-text:v1.5' not found.
       Pull it with: ollama pull nomic-embed-text:v1.5

RECOVERY STEPS:
1. Pull the required embedding model:
   ollama pull nomic-embed-text:v1.5
2. Verify it is installed:
   ollama list
3. Re-run your command.
"""
)

# =============================================================================
# SCENARIO 5: BOTH SERVICES DOWN
# =============================================================================

print(
    """
SCENARIO 5: Both OpenSearch AND Ollama Are Down
===============================================

RECOVERY STEPS:
1. Diagnose both at once:
   python scripts/check_setup.py
2. Start OpenSearch:
   cd docker && docker compose up -d opensearch
3. Start Ollama (another terminal):
   ollama serve
4. Re-run the diagnostic until all checks pass:
   python scripts/check_setup.py
"""
)

# =============================================================================
# SCENARIO 6: API SERVER WHEN OPENSEARCH IS DOWN
# =============================================================================

print(
    """
SCENARIO 6: API Server When OpenSearch is Down
==============================================

WHAT HAPPENS:
1. You run: python api_server.py
2. The server starts and listens on http://localhost:8000
3. GET /health reports the vector DB as unavailable until OpenSearch is up

RECOVERY STEPS:
1. Start OpenSearch (if not running):
   cd docker && docker compose up -d opensearch
2. The agent reconnects on the next request; verify:
   curl http://localhost:8000/health
"""
)

# =============================================================================
# DIAGNOSTIC TOOL
# =============================================================================

print(
    """
USING THE DIAGNOSTIC TOOL
==========================

Before running the loader or the API server:

    python scripts/check_setup.py

This verifies Ollama and the local OpenSearch connection and prints the KB index
in use, with recovery steps on any failure.
"""
)

# =============================================================================
# BEST PRACTICES
# =============================================================================

print(
    """
BEST PRACTICES
==============

1. ALWAYS RUN THE DIAGNOSTIC FIRST:
   python scripts/check_setup.py

2. ENSURE SERVICES ARE RUNNING:
   cd docker && docker compose ps
   pgrep ollama || echo "Ollama not running"

3. CHECK LOGS IF ISSUES PERSIST:
   docker compose -f docker/docker-compose.yml logs -f opensearch

4. WAIT FOR SERVICES TO INITIALIZE:
   OpenSearch can take 30-60 seconds to become healthy;
   Ollama model loading can take time on first use.
"""
)
