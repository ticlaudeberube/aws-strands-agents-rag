# Hallucination Prevention - Todo List

**Date Created**: April 18, 2026  
**Related Issue**: Cached response for "What is Milvus?" contained inaccurate information (FIXED ✅)  
**Status**: In Progress

---

## ✅ COMPLETED

- [x] Fix cached response for "What is Milvus?"
  - Removed "also known as MilvusDB" hallucination
  - Updated both `data/responses.json` and `data/responses_with_sources.json`
  - Result: Accurate description of Milvus based on actual KB content

---

## 📋 HIGH PRIORITY - Implement Soon

### 1. Audit Existing Cache for Hallucinations
- [ ] Review all Q&A pairs in `data/responses.json` for factual accuracy
- [ ] Check each cached answer matches information in actual knowledge base
- [ ] Document any inaccuracies found
- [ ] **Files to Review**: `data/responses.json`, `data/responses_with_sources.json`
- [ ] **Success Criteria**: All cached answers verified against KB sources
- [ ] **Estimated Effort**: 2-3 hours

### 2. Add Hallucination Detection Logic
- [ ] Implement validation in RAG worker to detect unsupported claims
- [ ] Validate generated answers against retrieved sources
- [ ] Add check: Does answer contain claims NOT in retrieved documents?
- [ ] Log warnings when hallucinations detected
- [ ] **Location**: `src/agents/strands_graph_agent.py` (RAG worker node)
- [ ] **Success Criteria**: Detects when LLM makes up facts not in sources
- [ ] **Estimated Effort**: 2-4 hours

### 3. Improve Cache Generation Process
- [ ] When initially populating cache, validate each answer against actual KB docs
- [ ] Cross-reference cached answers with Milvus documentation chunks
- [ ] Ensure answer only contains facts present in retrieved documents
- [ ] Document the validation process for future cache updates
- [ ] **Files to Update**: `document_loaders/sync_responses_cache.py` or new validation script
- [ ] **Success Criteria**: Cache population includes validation step
- [ ] **Estimated Effort**: 1-2 hours

---

## 🔄 MEDIUM PRIORITY - Implement Next Sprint

### 4. Implement Cache Quality Metrics
- [ ] Track which cached answers get flagged as inaccurate by users
- [ ] Log query execution path (cache hit vs KB search vs web search)
- [ ] Monitor cache hit accuracy over time
- [ ] Create dashboard or report of cache quality metrics
- [ ] **Location**: `api_server.py` metrics collection
- [ ] **Success Criteria**: Can identify low-quality cached answers
- [ ] **Estimated Effort**: 2-3 hours

### 5. Add Cache Confidence Scoring
- [ ] Score each cached answer based on source relevance
- [ ] Only return cached answer if confidence > threshold
- [ ] Fall back to KB search if cached answer has low confidence
- [ ] **Location**: `src/tools/response_cache.py`
- [ ] **Success Criteria**: Low-confidence cached answers trigger fallback
- [ ] **Estimated Effort**: 1-2 hours

---

## 🌐 LOWER PRIORITY - Research & Plan

### 6. Enable Web Search Fallback for Basic Questions
- [ ] For commonly asked questions (like "What is Milvus?"), enable web search validation
- [ ] Verify cached answer matches web search results
- [ ] Flag mismatches for manual review
- [ ] **Config Variable**: `WEB_SEARCH_CACHE_VALIDATION` (new)
- [ ] **Success Criteria**: Can validate cache against current web info
- [ ] **Estimated Effort**: 3-4 hours (requires Tavily API integration)

### 7. Create Cache Maintenance Procedures
- [ ] Document when/how to update cached answers
- [ ] Create process for validating new cache entries
- [ ] Schedule monthly cache quality audit
- [ ] Archive old/outdated cached answers
- [ ] **Files to Create**: `docs/CACHE_MAINTENANCE.md`
- [ ] **Success Criteria**: Documented procedures for cache lifecycle
- [ ] **Estimated Effort**: 1-2 hours (documentation only)

### 8. Implement Automated Cache Testing
- [ ] Add unit tests for cached Q&A pairs
- [ ] Test semantic similarity calculations
- [ ] Test entity validation preventing cross-product hits
- [ ] **Location**: `tests/test_response_cache.py`
- [ ] **Success Criteria**: Cache behavior validated by tests
- [ ] **Estimated Effort**: 2-3 hours

---

## 🎯 TESTING & VALIDATION

### Before Deploying Any Cache Changes

- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Test cache endpoint: `GET /v1/cache/responses`
- [ ] Manual validation: Query system with test questions
- [ ] Verify no regressions in response quality
- [ ] Check latency impact (cache should remain <100ms)

---

## 📊 Summary Table

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Audit existing cache | HIGH | 2-3h | ⏳ TODO |
| Add hallucination detection | HIGH | 2-4h | ⏳ TODO |
| Improve cache generation | HIGH | 1-2h | ⏳ TODO |
| Cache quality metrics | MEDIUM | 2-3h | ⏳ TODO |
| Cache confidence scoring | MEDIUM | 1-2h | ⏳ TODO |
| Web search validation | LOW | 3-4h | ⏳ TODO |
| Maintenance procedures | LOW | 1-2h | ⏳ TODO |
| Automated testing | LOW | 2-3h | ⏳ TODO |

---

## 🔗 Related Documentation

- [Cache Architecture Analysis](docs/archive/CACHE_ARCHITECTURE_ANALYSIS.md)
- [Caching Strategy](docs/CACHING_STRATEGY.md)
- [Web Search Integration](docs/WEB_SEARCH_INTEGRATION.md)
- [Response Cache Implementation](src/tools/response_cache.py)

---

## 💡 Notes

- **Root Cause**: Cache was pre-populated with manually-written answers that weren't validated against actual KB content
- **Current Safeguard**: Entity validation prevents cross-product cache hits (e.g., Pinecone answer won't be returned for Milvus query)
- **Next Step**: Start with HIGH priority tasks in Sprint 2
- **Team Assignment**: Assign cache audit and hallucination detection to ensure quality before any new caching
