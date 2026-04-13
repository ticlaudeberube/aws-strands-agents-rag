"""
ERROR HANDLING & RECOVERY GUIDE
What Happens When Services Don't Respond
========================================

This document describes what happens when Milvus or Ollama are not available,
and how to recover from these errors.
"""

# =============================================================================
# SCENARIO 1: MILVUS IS NOT RUNNING
# =============================================================================

print("""
SCENARIO 1: Milvus is Not Running
==================================

WHAT HAPPENS:
1. When you run: python document-loaders/load_milvus_docs_ollama.py

ERROR MESSAGE (Improved):
  ❌ Milvus Connection Failed!
     Error: Milvus connection failed at localhost:19530. Make sure Milvus is running.

     To fix this:
     1. Check if Milvus is running:
        cd docker && docker-compose ps
     2. If not running, start it:
        cd docker && docker-compose up -d
     3. Wait 30 seconds for Milvus to be ready
     4. Try again: python document-loaders/load_milvus_docs_ollama.py

HOW IT WORKS:
- The loader now initializes Milvus client at startup in the process() function
- If connection fails, it immediately exits with a user-friendly error
- Before: Raw pymilvus exception with no guidance
- Now: Clear error message with recovery steps

RECOVERY STEPS:
1. Start Milvus:
   cd docker
   docker-compose up -d

2. Wait ~30 seconds for services to be ready:
   docker-compose ps
   (Should show all services as "Up")

3. Run the loader again:
   python document-loaders/load_milvus_docs_ollama.py
""")

# =============================================================================
# SCENARIO 2: MILVUS IS SLOW/TIMING OUT
# =============================================================================

print("""
SCENARIO 2: Milvus is Starting but Slow
========================================

WHAT HAPPENS:
1. Milvus is running but not fully initialized
2. Connection timeouts occur during operations

ERROR MESSAGE:
  ⚠️  Warning: Could not check collection: Connection timed out
     Proceeding to create new collection...

HOW IT WORKS:
- The loader waits for Milvus to respond
- If it takes too long, it shows a warning and continues
- The operation may still complete if you wait longer

RECOVERY STEPS:
1. Wait longer for Milvus to start:
   docker-compose -f docker/docker-compose.yml logs -f
   (Look for "Milvus server started" messages)

2. Once fully initialized, try again:
   python document-loaders/load_milvus_docs_ollama.py
""")

# =============================================================================
# SCENARIO 3: OLLAMA IS NOT RUNNING
# =============================================================================

print("""
SCENARIO 3: Ollama is Not Running
==================================

WHAT HAPPENS:
1. When you run: python document-loaders/load_milvus_docs_ollama.py

ERROR MESSAGE (Improved):
  🔍 Checking Ollama...
    ❌ Cannot connect to Ollama at http://localhost:11434
       Make sure Ollama is running:
       - Run: ollama serve
       - Or on macOS: Open the Ollama app from Applications

HOW IT WORKS:
- The verify_ollama_setup() function checks Ollama before processing
- If unavailable, it raises an error immediately
- This prevents wasting time downloading docs and processing

RECOVERY STEPS:
1. Start Ollama:
   ollama serve
   (In a new terminal)

2. Run the loader:
   python document-loaders/load_milvus_docs_ollama.py
""")

# =============================================================================
# SCENARIO 4: EMBEDDING MODEL NOT AVAILABLE
# =============================================================================

print("""
SCENARIO 4: Embedding Model Not Available
===========================================

WHAT HAPPENS:
1. Ollama is running but required embedding model is not installed

ERROR MESSAGE (Improved):
  🔍 Checking Ollama...
    ✓ Ollama is running at http://localhost:11434
    ✓ Available models: 28 found
    ❌ Error: Embedding model 'nomic-embed-text:v1.5' not found
       Available models: llama3.2:1b, qwen2.5:0.5b, ...
       Pull the model with: ollama pull nomic-embed-text:v1.5

HOW IT WORKS:
- The verify_ollama_setup() function checks for required models
- It lists available models to help you understand what's installed
- It tells you exactly which command to run to fix it

RECOVERY STEPS:
1. Pull the required embedding model:
   ollama pull nomic-embed-text:v1.5

2. Verify it's installed:
   ollama list
   (Should show nomic-embed-text:v1.5 in the list)

3. Run the loader:
   python document-loaders/load_milvus_docs_ollama.py
""")

# =============================================================================
# SCENARIO 5: BOTH SERVICES DOWN
# =============================================================================

print("""
SCENARIO 5: Both Milvus AND Ollama Are Down
=============================================

WHAT HAPPENS:
1. You run: python document-loaders/load_milvus_docs_ollama.py
2. It tries to initialize both clients
3. Both fail

ERROR MESSAGE (First One):
  ❌ Failed to initialize Ollama client: Connection refused

HOW IT WORKS:
- The loader initializes Ollama first, then Milvus
- The first failure is reported and the script exits
- You need to fix services one at a time

RECOVERY STEPS:
1. Verify both services are needed:
   python check_setup.py
   (This checks both Ollama and Milvus)

2. Start Milvus:
   cd docker && docker-compose up -d

3. Start Ollama:
   ollama serve
   (In another terminal)

4. Run the diagnostic again:
   python check_setup.py

5. Once all ✓ checks pass, run the loader:
   python document-loaders/load_milvus_docs_ollama.py
""")

# =============================================================================
# SCENARIO 6: API SERVER (api_server.py) WHEN MILVUS DOWN
# =============================================================================

print("""
SCENARIO 6: API Server When Milvus is Down
===========================================

WHAT HAPPENS:
1. You run: python api_server.py
2. Server starts and listens on http://localhost:8000
3. You make a request: curl http://localhost:8000/health

ERROR MESSAGE:
  GET /health returns 500 error with Milvus connection error

HEALTH CHECK RESULT:
  {
    "error": "Milvus connection failed",
    "details": "..."
  }

HOW IT WORKS:
- The API server initializes RAGAgent when first request comes
- RAGAgent tries to initialize MilvusVectorDB
- If Milvus is down, the request fails with 500 error

PREVENTION:
- Use the diagnostic before starting the API server:
  python check_setup.py
  (Ensures both services are working)

RECOVERY STEPS:
1. Start Milvus (if not running):
   cd docker && docker-compose up -d

2. Restart the API server:
   python api_server.py

3. Try the request again:
   curl http://localhost:8000/health
""")

# =============================================================================
# DIAGNOSTIC TOOL
# =============================================================================

print("""
USING THE DIAGNOSTIC TOOL
==========================

To check if everything is configured correctly BEFORE running the loader:

    python check_setup.py

This will show:
  ✓ Ollama: OK
  ✓ Milvus: OK
  ✓ All checks passed! System is ready.

Or if there's an issue:
  ❌ Ollama: FAILED
  ✓ Milvus: OK
  ❌ Some checks failed. Please fix the issues above.

BENEFITS:
- Quick verification before long operations
- Clear error messages with recovery steps
- Lists available models in Ollama
- Shows collections in Milvus
""")

# =============================================================================
# SUMMARY TABLE
# =============================================================================

print("""
SUMMARY: Error Handling Improvements
=====================================

┌─────────────────┬──────────────────────────┬────────────────────────────┐
│ Service         │ Before (Raw Error)       │ After (User-Friendly)      │
├─────────────────┼──────────────────────────┼────────────────────────────┤
│ Milvus Down     │ pymilvus.exceptions      │ Clear error message with   │
│                 │ ConnectionError (raw)    │ recovery steps             │
├─────────────────┼──────────────────────────┼────────────────────────────┤
│ Ollama Down     │ requests.ConnectionError │ "Make sure Ollama is       │
│                 │ (no helpful message)     │ running: ollama serve"     │
├─────────────────┼──────────────────────────┼────────────────────────────┤
│ Missing Model   │ Hangs or cryptic error   │ "Run: ollama pull          │
│                 │                          │ nomic-embed-text:v1.5"     │
├─────────────────┼──────────────────────────┼────────────────────────────┤
│ Both Down       │ Both errors (confusing)  │ Clear initialization order │
│                 │                          │ with early exit            │
├─────────────────┼──────────────────────────┼────────────────────────────┤
│ Slow Response   │ Timeout without context  │ "Service not responding" + │
│                 │                          │ guidance                   │
└─────────────────┴──────────────────────────┴────────────────────────────┘
""")

# =============================================================================
# BEST PRACTICES
# =============================================================================

print("""
BEST PRACTICES
==============

1. ALWAYS RUN DIAGNOSTIC FIRST:
   python check_setup.py

2. ENSURE SERVICES ARE RUNNING:
   cd docker && docker-compose ps
   pgrep ollama || echo "Ollama not running"

3. CHECK LOGS IF ISSUES PERSIST:
   docker-compose -f docker/docker-compose.yml logs -f
   (In one terminal to monitor Milvus)

4. READ ERROR MESSAGES CAREFULLY:
   They now include the exact recovery steps

5. WAIT FOR SERVICES TO INITIALIZE:
   Milvus can take 30+ seconds to start
   Ollama model loading can take time
""")
