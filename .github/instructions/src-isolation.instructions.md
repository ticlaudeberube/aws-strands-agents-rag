# Source Isolation & Document Loader Architecture

This guide explains the intentional separation between the `src/` production package and the `document-loaders/` utility package in this project.

---

## 🏗️ The Core Architecture Decision

The project maintains **strict isolation** between two independent systems:

```
┌─────────────────────────────────────────────┐
│ src/ (Production Application)                │
│ ├── agents/                                 │
│ ├── tools/                                  │
│ ├── config/                                 │
│ └── ✅ NO imports from document-loaders/    │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ document-loaders/ (Data Pipeline Utility)    │
│ ├── core/                                   │
│ ├── local_settings.py                       │
│ └── ✅ NO imports from src/                 │
└─────────────────────────────────────────────┘
```

**Why This Design:**
- `src/` is a production application → should have minimal dependencies
- `document-loaders/` is a standalone utility → can run independently, be replaced, or deployed separately
- Each achieves its purpose without coupling to the other

---

## ✅ What This Means (Rules)

### Rule 1: src/ MUST NOT Import from document-loaders/
❌ **Never do this in src/ code:**
```python
from document_loaders.core.tools import MilvusVectorDB  # WRONG
from document_loaders.local_settings import Settings    # WRONG
```

✅ **Instead, duplicate the implementation in src/:**
```python
# src/tools/milvus_client.py
from src.config.settings import Settings

class MilvusVectorDB:
    """Production-grade MilvusVectorDB implementation"""
```

**Why:** Production code should not depend on data pipeline utilities.

---

### Rule 2: document-loaders/ MUST NOT Import from src/
❌ **Never do this in document-loaders code:**
```python
from src.config.settings import Settings        # WRONG
from src.agents.strands_graph_agent import Agent # WRONG
```

✅ **Instead, use local implementation:**
```python
# document_loaders/local_settings.py
import os
from pathlib import Path

class Settings:
    """Local settings for document loader only"""
    MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
    # ... loader-specific config
```

**Why:** Document loader must remain a standalone utility, deployable anywhere (Docker, Lambda, CI/CD, etc.).

---

### Rule 3: Duplicate Code Between src/ and document-loaders/ is OK
✅ **This is intentional and correct:**
```
src/tools/milvus_client.py       ← Production MilvusVectorDB
document_loaders/core/tools.py   ← Utility MilvusVectorDB
```

This is **NOT** a violation of DRY. Each serves a different purpose:
- `src/tools/milvus_client.py` - Part of production app, uses app settings
- `document_loaders/core/tools.py` - Standalone utility, uses loader settings

They can be updated independently without affecting each other.

---

### Rule 4: Each Package Has Its Own Configuration
✅ **This is intentional and correct:**
```
src/config/settings.py                ← App configuration
document_loaders/local_settings.py    ← Loader configuration
```

These can be completely different:
```python
# src/config/settings.py - Production
MODEL_NAME = "llama3.1:8b"  # Powerful model for production
MILVUS_COLLECTION_TIMEOUT = 30

# document_loaders/local_settings.py - Utility
MODEL_NAME = "qwen2.5:0.5b"  # Fast model for data loading
BATCH_SIZE = 50
```

**Why:** Loader and app have different requirements and can be tuned independently.

---

## 🎯 When to Add New Code

### I'm Adding a Production Feature
**Question: Where should it go?**

✅ Goes in `src/`:
- Logic for Strands agents
- Tools used by agents (search, generation, etc.)
- Production configuration
- API endpoints
- Production utilities

❌ Should NOT use document_loaders code

**Example:**
```python
# ✅ CORRECT: New tool in src/
# src/tools/tavily_search.py
from src.config.settings import Settings

class TavilySearchClient:
    def __init__(self):
        self.api_key = Settings.TAVILY_API_KEY
```

---

### I'm Adding a Data Loading Feature
**Question: Where should it go?**

✅ Goes in `document-loaders/`:
- Scripts to ingest data
- Document processing utilities
- Embedding and indexing logic
- Local configuration

❌ Should NOT import from src/

**Example:**
```python
# ✅ CORRECT: New loader in document-loaders/
# document_loaders/pdf_loader.py
from document_loaders.local_settings import Settings
from document_loaders.core.tools import MilvusVectorDB

class PDFDocumentLoader:
    def __init__(self):
        self.db = MilvusVectorDB(Settings.MILVUS_HOST)
```

---

## 🔄 Sharing Logic Between src/ and document-loaders/

Sometimes you need the same logic in both places (e.g., MilvusVectorDB).

### Option A: Duplicate (Current Approach) ✅
```
src/tools/milvus_client.py
document_loaders/core/tools.py
```
**Benefit:** Complete independence, can be updated separately
**Cost:** Small code duplication

### Option B: Thin Wrapper (If Loader Must Depend on Something)
If the loader needed to use `src.config.settings`:
```python
# document_loaders/local_settings.py
try:
    from src.config.settings import Settings
except ImportError:
    # Fallback to local config if src/ not available
    class Settings:
        MILVUS_HOST = "localhost"
```

**Benefit:** Single source of truth with fallback
**Cost:** Light dependency on src structure

### Best Practice: Keep It Simple
Use Option A (duplicate). It's clearer and cleaner than trying to share.

---

## 🧪 Testing Both Packages

### Testing src/ (Production)
```bash
# Test runs against src/ only
# Document loader is NOT imported
pytest tests/
```

✅ Use this for:
- Agent tests
- Tool tests
- API endpoint tests

---

### Testing document-loaders/ (Utility)
```bash
# Can run standalone, no src/ required
python document_loaders/sync_responses_cache.py
```

✅ Verification commands:
```bash
# Verify loader has no src imports
python -m py_compile document_loaders/sync_responses_cache.py

# Check imports
grep -r "from src" document_loaders/
grep -r "import src" document_loaders/
```

---

## 🚫 Common Mistakes to Avoid

| Mistake | Why It's Wrong | Fix |
|---------|---|---|
| Importing loader in src/ | Production code depends on utility | Duplicate the implementation in src/ |
| Importing src/ in loader | Loader loses independence | Use local_settings.py instead |
| Sharing settings files | Config drift between packages | Each package defines its own config |
| Using src.tools in loader | Couples loader to production | Reimplement in document_loaders/core/ |
| Circular imports | Breaks both packages | Keep dependencies one-way only |

---

## 📋 PR Review Checklist

When reviewing code additions, check:

- [ ] New code in `src/` does NOT import from `document-loaders/`
- [ ] New code in `document-loaders/` does NOT import from `src/`
- [ ] Configuration is in the right place (app config in src/, loader config in document-loaders/)
- [ ] Each package can be tested independently
- [ ] If code is duplicated, it's intentional (different packages, different purposes)

---

## ✨ Benefits of This Architecture

1. **Modularity:** Each part can be understood, tested, and deployed independently
2. **Flexibility:** Can upgrade, replace, or remove the loader without affecting production app
3. **Clarity:** No hidden dependencies or coupling surprises
4. **Deployability:** Loader can run on schedule, Docker container, Lambda, etc. without production package
5. **Maintainability:** Changes to one package don't force changes to the other

---

**Last Updated:** April 16, 2026
