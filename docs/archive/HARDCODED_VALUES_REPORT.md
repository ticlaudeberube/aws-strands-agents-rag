# Hardcoded Values Scan Report

## Summary
This document identifies all remaining hardcoded configuration values in the codebase that should be considered for externalization to environment variables.

## Critical Findings

### Category 1: Index Parameters (HIGH PRIORITY)
These control Milvus collection indexing behavior and should be externalized for deployment-specific optimization.

**File: `src/tools/milvus_client.py` (lines 136-144)**
- HNSW Index:
  - `"M": 30` - Maximum number of connections per element
  - `"efConstruction": 200` - Size of dynamic list for construction
- IVF_FLAT Index:
  - `"nlist": 128` - Number of clusters

**Impact**: These parameters directly affect index creation and search performance. Different deployments may need different values:
- Development: Keep HNSW defaults for speed
- Large-scale: IVF_FLAT with larger nlist for scalability
- Testing: Tune for accuracy vs speed tradeoffs

**Recommendation**: Externalize as `MILVUS_HNSW_M`, `MILVUS_HNSW_EF_CONSTRUCTION`, `MILVUS_IVF_NLIST`

---

### Category 2: Search Parameters (MEDIUM PRIORITY)
These affect query performance after index creation.

**File: `src/tools/milvus_client.py` (line 272)**
- `search_params = {"ef": 64}` - HNSW search parameter
  - `"ef": 64` - Determines search accuracy/speed tradeoff

**Usage**: Applied in `search()` method when no custom search_params provided

**Impact**: Direct effect on search latency and accuracy
- Lower ef (e.g., 16): Faster searches, slightly lower accuracy
- Higher ef (e.g., 128): More accurate, slower searches
- Current 64: Balanced setting

**Recommendation**: Externalize as `MILVUS_SEARCH_EF` (with default 64)

---

### Category 3: Default Retrieval Limits (MEDIUM PRIORITY)
Default values for retrieval operations should be configurable.

**File: `src/agents/strands_rag_agent.py` (multiple locations)**

- Line 682: `top_k: int = 2` in `search_comparison()` method
- Line 1671: `top_k: int = 10` in `answer_question_no_cache()`
- Line 1910: `top_k: int = 10` in other retrieval methods
- Line 2073: `top_k: int = 10` (another retrieval method)

**Usage**: Controls how many context chunks retrieved from vector DB

**Impact**:
- Lower top_k (2): Faster, focused retrieval, may miss context
- Higher top_k (10+): Slower, more comprehensive context, potential noise

**Recommendation**: Create `DEFAULT_TOP_K=10` and use throughout, plus `SEARCH_COMPARISON_TOP_K=2`

---

### Category 4: Cache TTL (MEDIUM PRIORITY)
Embedding cache time-to-live affects freshness vs performance.

**File: `src/agents/strands_rag_agent.py` (line 113)**
- `embedding_cache_ttl: int = 3600` - 1 hour in seconds

**Usage**: Constructor parameter in `StrandsRAGAgent.__init__()`

**Current**: 3600 seconds = 1 hour
- Development: Could be shorter (e.g., 300s / 5min for testing)
- Production: Could be longer (e.g., 86400s / 24 hours)

**Recommendation**: Externalize as `EMBEDDING_CACHE_TTL=3600` (seconds)

---

### Category 5: Collection Names (LOW PRIORITY)
Hard-coded collection names limit flexibility.

**File: `src/tools/response_cache.py` (line 23)**
- `CACHE_COLLECTION = "response_cache"` - Response cache collection name

**File: `src/agents/strands_rag_agent.py` (line 682)**
- `collection_name: str = "milvus_docs"` - Default collection for searches

**Usage**:
- `response_cache` for semantic response caching
- `milvus_docs` for context retrieval in searches

**Impact**: Low - these are class defaults that can be overridden per call
- Used as fallback when collection not specified
- Separate instance for each use case reduces collision risk

**Recommendation**: Make these configurable but lower priority than others
- `RESPONSE_CACHE_COLLECTION_NAME=response_cache`
- `DEFAULT_MILVUS_DOCS_COLLECTION=milvus_docs`

---

### Category 6: Score Keywords (LOW-MEDIUM PRIORITY)
Hard-coded keyword evaluation scores for scope classification.

**File: `src/agents/strands_rag_agent.py` (lines 327-329, and more)**
```python
in_scope_keywords = {
    "milvus": 10,
    "vector database": 10,
    "vector db": 10,
    "vector search": 9,
    # ... (many more with hardcoded scores 5-10)
}
```

**Usage**: Fast keyword-based pre-filter for scope detection

**Impact**: Controls which questions are considered in-scope for Milvus documentation
- Higher scores = more likely to match
- These are relative importance weights for NLP/ML logic
- Very domain-specific to Milvus documentation

**Recommendation**: Could be externalized but less critical
- Complex to manage as simple env vars
- Consider extracting to JSON config file if customization needed
- Not urgent for now

---

### Category 7: Already Externalized - Settings Class
The following are ALREADY properly externalized in Settings class:

✅ **Properly Configured in `src/config/settings.py`:**
- `ollama_host` (env: OLLAMA_HOST)
- `ollama_model` (env: OLLAMA_MODEL)
- `ollama_embed_model` (env: OLLAMA_EMBEDDING_MODEL)
- `ollama_timeout` (hardcoded 30, could be env: OLLAMA_TIMEOUT)
- `ollama_pool_size` (hardcoded 5, could be env: OLLAMA_POOL_SIZE)
- `milvus_host` (hardcoded localhost, should be env: MILVUS_HOST)
- `milvus_port` (hardcoded 19530, should be env: MILVUS_PORT)
- `milvus_db_name` (env: MILVUS_DB_NAME)
- `milvus_user` (hardcoded root, could be env: MILVUS_USER)
- `milvus_password` (hardcoded Milvus, could be env: MILVUS_PASSWORD)
- `milvus_timeout` (hardcoded 30, could be env: MILVUS_TIMEOUT)
- `milvus_pool_size` (hardcoded 10, could be env: MILVUS_POOL_SIZE)
- `milvus_index_type` (env: MILVUS_INDEX_TYPE) - Phase 1b ✅
- `milvus_metric_type` (env: MILVUS_METRIC_TYPE) - Phase 1b ✅
- `embedding_dim` (env: EMBEDDING_DIM)
- `response_cache_embedding_dim` (env: RESPONSE_CACHE_EMBEDDING_DIM)
- `response_cache_threshold` (env: RESPONSE_CACHE_THRESHOLD) - Phase 2 ✅
- `max_chunk_length` (hardcoded 250, could be env: MAX_CHUNK_LENGTH)
- `max_tokens` (hardcoded 256, could be env: MAX_TOKENS)
- `agent_cache_size` (hardcoded 500, could be env: AGENT_CACHE_SIZE)
- `api_port` (env: API_PORT)
- `web_search_timeout` (env: WEB_SEARCH_TIMEOUT)

---

## Recommended Externalization Order

### Phase 3A (HIGH PRIORITY - Index Tuning)
Enables critical performance optimizations:
1. `MILVUS_HNSW_M` (default: 30)
2. `MILVUS_HNSW_EF_CONSTRUCTION` (default: 200)
3. `MILVUS_IVF_NLIST` (default: 128)
4. `MILVUS_SEARCH_EF` (default: 64)

**Effort**: ~2 hours | **Impact**: High (enables deployment-specific tuning)

### Phase 3B (MEDIUM PRIORITY - Retrieval Tuning)
Affects retrieval and response quality:
1. `DEFAULT_TOP_K` (default: 10)
2. `SEARCH_COMPARISON_TOP_K` (default: 2)
3. `EMBEDDING_CACHE_TTL` (default: 3600)

**Effort**: ~1.5 hours | **Impact**: Medium (runtime behavior tuning)

### Phase 3C (LOW PRIORITY - Collection Names)
Nice to have but lower impact:
1. `RESPONSE_CACHE_COLLECTION_NAME` (default: "response_cache")
2. `DEFAULT_MILVUS_DOCS_COLLECTION` (default: "milvus_docs")

**Effort**: ~1 hour | **Impact**: Low (easy override already possible)

### Phase 3D (FUTURE - Keyword Scores)
Complex and domain-specific:
- Extract keyword scores to JSON config file
- Load dynamically at startup
- Not urgent unless fine-tuning scope detection

**Effort**: ~3-4 hours | **Impact**: Low (very domain-specific)

---

## Statistics

- **Total Hardcoded Values Found**: ~15-20
- **Already Externalized via Settings**: ~27
- **High Priority to Externalize**: 4
- **Medium Priority**: 5
- **Low Priority**: 2-4

---

## Next Steps

1. **Immediate**: Review Phase 3A (index parameters) - most impactful
2. **Short-term**: Implement Phase 3B (retrieval tuning)
3. **Optional**: Phase 3C (collection names) if needed
4. **Future**: Phase 3D (keyword scoring) if customization required

---

## Code Examples

### Phase 3A - Index Parameters (Proposed)
```python
# In settings.py
milvus_hnsw_m: int = int(os.getenv("MILVUS_HNSW_M", "30"))
milvus_hnsw_ef_construction: int = int(os.getenv("MILVUS_HNSW_EF_CONSTRUCTION", "200"))
milvus_ivf_nlist: int = int(os.getenv("MILVUS_IVF_NLIST", "128"))
milvus_search_ef: int = int(os.getenv("MILVUS_SEARCH_EF", "64"))

# In milvus_client.py create_collection()
if index_type == "HNSW":
    index_params["params"] = {
        "M": settings.milvus_hnsw_m,
        "efConstruction": settings.milvus_hnsw_ef_construction,
    }
```

### Phase 3B - Retrieval Tuning (Proposed)
```python
# In settings.py
default_top_k: int = int(os.getenv("DEFAULT_TOP_K", "10"))
search_comparison_top_k: int = int(os.getenv("SEARCH_COMPARISON_TOP_K", "2"))
embedding_cache_ttl: int = int(os.getenv("EMBEDDING_CACHE_TTL", "3600"))

# In strands_rag_agent.py
def search_comparison(..., top_k: Optional[int] = None):
    top_k = top_k or self.settings.search_comparison_top_k
```

---

## Files Affected by Changes

- `src/config/settings.py` - Add new configuration settings
- `src/tools/milvus_client.py` - Use settings for index and search params
- `src/agents/strands_rag_agent.py` - Use settings for top_k and cache TTL
- `.env.example` - Document new environment variables
- `.env` - Add development values
- `docs/DEVELOPMENT.md` - Update configuration reference
