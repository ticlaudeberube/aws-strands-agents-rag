# Caching Strategy Improvement Recommendations

**Document Version**: 1.0
**Last Updated**: March 7, 2026
**Target Platform**: Container-based deployment (ECS/Fargate, EC2, Docker)
**Status**: Proposal / Implementation Roadmap

> **📌 Deploying with AWS Lambda + AgentCore?**
> See [AGENTCORE_CACHING_STRATEGY.md](AGENTCORE_CACHING_STRATEGY.md) for serverless-specific recommendations.
> Key differences: ElastiCache Redis replaces in-memory caches, DynamoDB analytics replaces file-based tracking.

---

## Executive Summary

This document outlines concrete enhancements to improve the current single-layer Response Cache implementation. The recommendations are prioritized by effort vs impact, with implementation code examples and expected performance metrics.

**Current State**: Single-layer semantic caching via Milvus Response Cache
**Target Goal**: Multi-layer caching with 300-400ms additional speedup and 40-60% higher hit rates

---

## 🎯 High-Priority Improvements (Quick Wins)

### 1. Add Embedding Cache

**Current Problem**: Every question generates a new embedding (~256ms), even for repeat questions
**Effort**: Low | **Impact**: High | **Priority**: ⭐⭐⭐

#### Expected Benefit
- **Latency**: 256ms → 0ms for cached embeddings
- **Throughput**: 40-60% reduction in Ollama API calls
- **Storage**: In-memory only (no persistence overhead)

#### Implementation

```python
# In src/agents/strands_graph_agent.py - StrandsGraphRAGAgent.__init__
from collections import OrderedDict

class StrandsGraphRAGAgent:
    def __init__(self, settings: Settings):
        # ... existing initialization ...

        # NEW: Embedding cache (in-memory LRU)
        self.embedding_cache = OrderedDict()  # question → embedding vector
        self.max_cache_size = settings.agent_cache_size  # Use existing setting!

        # ... rest of initialization ...

    def _get_cached_embedding(self, text: str) -> List[float]:
        """Get embedding with automatic LRU caching.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (from cache or freshly generated)
        """
        # Check cache first
        if text in self.embedding_cache:
            logger.debug("✓ Embedding cache HIT")
            return self.embedding_cache[text]

        # Generate fresh embedding
        logger.debug("✗ Embedding cache MISS")
        embedding = self.ollama_client.embed_text(
            text,
            model=self.settings.ollama_embed_model
        )

        # Store with LRU eviction
        self.embedding_cache[text] = embedding
        if len(self.embedding_cache) > self.max_cache_size:
            self.embedding_cache.popitem(last=False)  # Remove oldest entry
            logger.debug(f"Evicted oldest embedding (cache size: {len(self.embedding_cache)})")

        return embedding
```

#### Configuration

**Use existing setting** (currently unused):
```bash
# In .env (already exists)
AGENT_CACHE_SIZE=500  # Now used for embedding cache LRU limit
```

**Optional: Enable/disable via flag**:
```bash
# Add to .env
ENABLE_EMBEDDING_CACHE=true
```

#### Integration Points

Update all `embed_text()` calls to use `_get_cached_embedding()`:
- `retrieve_context()` - When searching knowledge base
- `stream_answer()` - When checking response cache
- `answer_question()` - Main entry point

#### Testing

```python
# Test cache hit
embedding1 = agent._get_cached_embedding("What is Milvus?")
embedding2 = agent._get_cached_embedding("What is Milvus?")  # Should hit cache
assert embedding1 == embedding2
assert len(agent.embedding_cache) == 1

# Test LRU eviction
agent.max_cache_size = 2
for i in range(5):
    agent._get_cached_embedding(f"Question {i}")
assert len(agent.embedding_cache) == 2  # Only keeps 2 most recent
```

---

### 2. Add Search Results Cache

**Current Problem**: Same question queries Milvus multiple times
**Effort**: Low | **Impact**: Medium | **Priority**: ⭐⭐

#### Expected Benefit
- **Latency**: 10-30ms savings per search
- **Throughput**: 30-50% reduction in Milvus queries
- **Consistency**: Same results for identical queries

#### Implementation

```python
# In src/agents/strands_graph_agent.py - StrandsGraphRAGAgent.__init__
class StrandsGraphRAGAgent:
    def __init__(self, settings: Settings):
        # ... existing initialization ...

        # NEW: Search results cache (in-memory LRU)
        self.search_cache = OrderedDict()  # (collection, query, top_k) → results

        # ... rest of initialization ...

    def retrieve_context_cached(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
    ) -> Tuple[List[str], List[Dict]]:
        """Retrieve context with search result caching.

        Args:
            collection_name: Milvus collection to search
            query: Question text
            top_k: Number of results to retrieve

        Returns:
            Tuple of (context_chunks, sources)
        """
        # Create cache key
        cache_key = (collection_name, query, top_k)

        # Check cache
        if cache_key in self.search_cache:
            logger.debug("✓ Search cache HIT")
            return self.search_cache[cache_key]

        # Perform search (cache miss)
        logger.debug("✗ Search cache MISS")
        context, sources = self.retrieve_context(collection_name, query, top_k)

        # Cache results with LRU eviction
        self.search_cache[cache_key] = (context, sources)
        if len(self.search_cache) > self.max_cache_size:
            self.search_cache.popitem(last=False)
            logger.debug(f"Evicted oldest search result (cache size: {len(self.search_cache)})")

        return context, sources
```

#### Configuration

```bash
# Add to .env
ENABLE_SEARCH_CACHE=true
SEARCH_CACHE_SIZE=500  # Or use AGENT_CACHE_SIZE
```

#### Integration

Replace `retrieve_context()` calls with `retrieve_context_cached()` in:
- `rag_worker_node()` - Main RAG pipeline
- `answer_question()` - Direct answer method
- `stream_answer()` - Streaming response method

#### Testing

```python
# Test cache hit
context1, sources1 = agent.retrieve_context_cached("milvus_docs", "What is Milvus?", 5)
context2, sources2 = agent.retrieve_context_cached("milvus_docs", "What is Milvus?", 5)
assert context1 == context2
assert sources1 == sources2
assert len(agent.search_cache) == 1

# Test different parameters create new cache entry
context3, _ = agent.retrieve_context_cached("milvus_docs", "What is Milvus?", 10)  # Different top_k
assert len(agent.search_cache) == 2
```

---

### 3. Implement Cache TTL (Time-To-Live)

**Current Problem**: Cached answers never expire, even when documentation updates
**Effort**: Medium | **Impact**: High | **Priority**: ⭐⭐⭐

#### Expected Benefit
- **Freshness**: Automatic answer refresh when docs update
- **Accuracy**: Prevents serving outdated content
- **Configurability**: Different TTLs for dev/staging/prod

#### Implementation

```python
# In src/tools/response_cache.py
from datetime import datetime, timedelta

class MilvusResponseCache:
    def store_response(
        self,
        question: str,
        question_embedding: List[float],
        response: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Store response with TTL metadata.

        Args:
            question: Question text
            question_embedding: Question embedding vector
            response: Generated answer
            metadata: Additional metadata (collection, sources, etc.)
        """
        from src.config.settings import get_settings
        settings = get_settings()

        if metadata is None:
            metadata = {}

        # Add TTL metadata
        metadata.update({
            "question": question,
            "entity": self._extract_main_entity(question),
            "timestamp": datetime.now().isoformat(),
            "ttl_hours": settings.response_cache_ttl_hours,
            "doc_version": metadata.get("doc_version", "unknown"),
        })

        # ... rest of store logic ...

    def search_cache(
        self,
        question: str,
        question_embedding: List[float],
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        limit: int = 1,
    ) -> Optional[Dict]:
        """Search cache with TTL validation.

        Returns None if cached entry is expired.
        """
        # ... existing search logic ...

        # Extract metadata from best match
        metadata = best_match.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        # Validate TTL
        timestamp_str = metadata.get("timestamp")
        ttl_hours = metadata.get("ttl_hours", 24)

        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                age_hours = (datetime.now() - timestamp).total_seconds() / 3600

                if age_hours > ttl_hours:
                    logger.info(
                        f"Cache entry EXPIRED (age: {age_hours:.1f}h, TTL: {ttl_hours}h) - "
                        f"cached question: '{metadata.get('question', '')[:60]}'"
                    )
                    if hasattr(self, "metrics"):
                        self.metrics["ttl_expirations"] += 1
                    return None  # Force regeneration

                logger.debug(f"Cache entry valid (age: {age_hours:.1f}h, TTL: {ttl_hours}h)")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid timestamp format: {timestamp_str} - {e}")

        # ... rest of validation and return logic ...
```

#### Configuration

```python
# In src/config/settings.py
class Settings(BaseSettings):
    # ... existing settings ...

    response_cache_ttl_hours: int = Field(
        default=24,
        validation_alias="RESPONSE_CACHE_TTL_HOURS",
    )
```

```bash
# Add to .env
RESPONSE_CACHE_TTL_HOURS=24  # Expire cached answers after 24 hours

# Environment-specific values:
# Development: RESPONSE_CACHE_TTL_HOURS=1   (1 hour for rapid testing)
# Staging:     RESPONSE_CACHE_TTL_HOURS=6   (6 hours for testing)
# Production:  RESPONSE_CACHE_TTL_HOURS=24  (24 hours for stability)
```

#### Testing

```python
# Test TTL expiration
cache.store_response(
    question="What is Milvus?",
    question_embedding=[0.1] * 768,
    response="Milvus is...",
    metadata={"timestamp": (datetime.now() - timedelta(hours=25)).isoformat()}  # 25 hours ago
)

# Should return None (expired)
result = cache.search_cache("What is Milvus?", [0.1] * 768)
assert result is None
```

---

### 4. Add Cache Hit Rate Metrics

**Current Problem**: No visibility into cache effectiveness
**Effort**: Low | **Impact**: High | **Priority**: ⭐⭐⭐

#### Expected Benefit
- **Visibility**: Real-time cache performance monitoring
- **Optimization**: Data-driven threshold tuning
- **Debugging**: Identify cache issues quickly

#### Implementation

```python
# In src/tools/response_cache.py
class MilvusResponseCache:
    def __init__(self, ...):
        # ... existing initialization ...

        # NEW: Metrics tracking
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "entity_rejections": 0,
            "ttl_expirations": 0,
            "total_searches": 0,
        }

    def search_cache(self, ...) -> Optional[Dict]:
        """Search cache with metrics tracking."""
        self.metrics["total_searches"] += 1

        # ... existing search logic ...

        # Track hit/miss
        if cached_result:
            self.metrics["hits"] += 1
            logger.debug(f"Cache HIT (total: {self.metrics['hits']})")
        else:
            self.metrics["misses"] += 1
            logger.debug(f"Cache MISS (total: {self.metrics['misses']})")

        # Track entity rejection (if validation failed)
        if entity_mismatch:
            self.metrics["entity_rejections"] += 1

        return cached_result

    def get_hit_rate(self) -> Dict:
        """Get cache performance metrics.

        Returns:
            Dict with hit rate, counts, and performance stats
        """
        total = self.metrics["hits"] + self.metrics["misses"]

        return {
            "hit_rate": self.metrics["hits"] / total if total > 0 else 0.0,
            "hit_rate_percent": f"{(self.metrics['hits'] / total * 100) if total > 0 else 0:.1f}%",
            "hits": self.metrics["hits"],
            "misses": self.metrics["misses"],
            "entity_rejections": self.metrics["entity_rejections"],
            "ttl_expirations": self.metrics["ttl_expirations"],
            "total_searches": self.metrics["total_searches"],
            "cache_size": self.get_cache_size(),
        }

    def reset_metrics(self) -> None:
        """Reset metrics counters (useful for benchmarking)."""
        for key in self.metrics:
            self.metrics[key] = 0
```

#### API Endpoint Integration

```python
# In api_server.py
@app.get("/health/detailed", tags=["health"])
async def health_detailed():
    """Detailed health check with cache metrics."""
    agent = await get_or_init_agent()

    cache_metrics = {
        "embedding_cache": {
            "enabled": hasattr(agent, "embedding_cache"),
            "size": len(agent.embedding_cache) if hasattr(agent, "embedding_cache") else 0,
            "max_size": agent.max_cache_size if hasattr(agent, "max_cache_size") else 0,
        },
        "search_cache": {
            "enabled": hasattr(agent, "search_cache"),
            "size": len(agent.search_cache) if hasattr(agent, "search_cache") else 0,
            "max_size": agent.max_cache_size if hasattr(agent, "max_cache_size") else 0,
        },
        "response_cache": {},
    }

    # Add response cache metrics if available
    if hasattr(agent, "response_cache") and agent.response_cache:
        try:
            cache_metrics["response_cache"] = agent.response_cache.get_hit_rate()
        except Exception as e:
            logger.warning(f"Failed to get response cache metrics: {e}")
            cache_metrics["response_cache"] = {"error": str(e)}

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_metrics": cache_metrics,
        "agent_type": "StrandsGraphRAGAgent",
    }
```

#### Usage

```bash
# Check cache metrics
curl http://localhost:8000/health/detailed | jq '.cache_metrics'

# Expected output:
{
  "embedding_cache": {
    "enabled": true,
    "size": 245,
    "max_size": 500
  },
  "search_cache": {
    "enabled": true,
    "size": 189,
    "max_size": 500
  },
  "response_cache": {
    "hit_rate": 0.68,
    "hit_rate_percent": "68.0%",
    "hits": 340,
    "misses": 160,
    "entity_rejections": 12,
    "ttl_expirations": 8,
    "total_searches": 500,
    "cache_size": 156
  }
}
```

---

## 🚀 Medium-Priority Improvements

### 5. Use `agent_cache_size` Setting

**Current Problem**: `AGENT_CACHE_SIZE=500` exists but is not used
**Effort**: Trivial | **Impact**: Low | **Priority**: ⭐⭐

#### Solution

Simply connect the existing setting to the new caches (already shown in #1 and #2 above).

**No code changes needed** - improvements #1 and #2 already use `settings.agent_cache_size`.

#### Cleanup

Remove misleading comment:
```python
# In src/config/settings.py
# OLD (misleading):
agent_cache_size: int = 500  # LRU cache size for embeddings, searches, and answers

# NEW (accurate):
agent_cache_size: int = 500  # LRU cache size for embedding and search caches
```

---

### 6. Add Negative Caching

**Current Problem**: "No results found" queries re-search Milvus every time
**Effort**: Low | **Impact**: Medium | **Priority**: ⭐⭐

#### Expected Benefit
- Avoid repeated failed searches
- Faster response for unanswerable questions
- Reduced Milvus load

#### Implementation

```python
# In src/agents/strands_graph_agent.py
class StrandsGraphRAGAgent:
    def __init__(self, settings: Settings):
        # ... existing initialization ...

        # NEW: Negative cache (unanswerable questions)
        self.negative_cache = OrderedDict()  # question → expiry timestamp
        self.negative_cache_ttl = settings.negative_cache_ttl_seconds

    def retrieve_context_with_negative_cache(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
    ) -> Tuple[List[str], List[Dict]]:
        """Retrieve context with negative caching for failed searches.

        Returns empty results immediately if question recently failed.
        """
        # Check negative cache
        if query in self.negative_cache:
            expiry = self.negative_cache[query]
            if datetime.now() < expiry:
                logger.debug(
                    f"✓ Negative cache HIT - skipping search "
                    f"(expires in {(expiry - datetime.now()).seconds}s)"
                )
                return [], []  # Return empty results
            else:
                # Expired - remove from cache
                del self.negative_cache[query]

        # Perform search
        context, sources = self.retrieve_context_cached(collection_name, query, top_k)

        # Cache negative result if no results found
        if not context or len(context) == 0:
            expiry = datetime.now() + timedelta(seconds=self.negative_cache_ttl)
            self.negative_cache[query] = expiry
            logger.debug(
                f"Cached negative result (TTL: {self.negative_cache_ttl}s, "
                f"expires: {expiry.isoformat()})"
            )

            # LRU eviction for negative cache
            if len(self.negative_cache) > 100:  # Keep small (separate from main cache)
                self.negative_cache.popitem(last=False)

        return context, sources
```

#### Configuration

```python
# In src/config/settings.py
class Settings(BaseSettings):
    # ... existing settings ...

    negative_cache_ttl_seconds: int = Field(
        default=300,  # 5 minutes
        validation_alias="NEGATIVE_CACHE_TTL_SECONDS",
    )
```

```bash
# Add to .env
ENABLE_NEGATIVE_CACHE=true
NEGATIVE_CACHE_TTL_SECONDS=300  # Cache "no results" for 5 minutes
```

#### Use Cases

Best for:
- Typos or malformed questions
- Out-of-scope questions that will never have results
- Repeated probing/testing queries

---

### 7. Optimize Similarity Threshold

**Current Problem**: 0.99 threshold is very strict (likely reducing hit rate)
**Effort**: Zero (config only) | **Impact**: Medium | **Priority**: ⭐⭐

#### Recommendation

Test lower thresholds with monitoring:

```bash
# Current (very strict)
RESPONSE_CACHE_THRESHOLD=0.99  # 99% similarity required

# Recommended trials:
RESPONSE_CACHE_THRESHOLD=0.95  # 95% (balanced - START HERE)
RESPONSE_CACHE_THRESHOLD=0.92  # 92% (looser)
RESPONSE_CACHE_THRESHOLD=0.90  # 90% (risky - may increase false positives)
```

#### Testing Strategy

**Week 1**: Baseline with 0.99
- Monitor hit rate via `/health/detailed`
- Record sample questions that hit/miss

**Week 2**: Test with 0.95
- Deploy with new threshold
- Monitor for:
  - ✅ Increased hit rate (target: +20-30%)
  - ❌ Incorrect answers (false positives)
- Review logs for entity rejection rate

**Week 3**: Analyze results
- Compare hit rates: 0.99 vs 0.95
- Check accuracy: Review cached answers manually
- Decide: Keep 0.95 or try 0.92

**Decision Matrix**:
| Threshold | Hit Rate Estimate | False Positive Risk | Recommendation |
|-----------|-------------------|---------------------|----------------|
| 0.99 | Baseline (likely 40-50%) | Very low | Current setting |
| 0.95 | +20-30% | Low | **Recommended trial** |
| 0.92 | +40-50% | Medium | Trial if 0.95 succeeds |
| 0.90 | +60%+ | High | Not recommended |

---

### 8. Add Cache Compression

**Current Problem**: Large answers consume Milvus storage
**Effort**: Medium | **Impact**: Low (only at scale) | **Priority**: ⭐

#### Expected Benefit
- 60-80% storage reduction for long answers
- <1ms overhead per compression/decompression
- Significant at scale (10,000+ cached entries)

#### Implementation

```python
# In src/tools/response_cache.py
import gzip
import base64

class MilvusResponseCache:
    def store_response(
        self,
        question: str,
        question_embedding: List[float],
        response: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Store response with optional compression."""
        from src.config.settings import get_settings
        settings = get_settings()

        if metadata is None:
            metadata = {}

        # Compress answers larger than threshold
        if (
            settings.enable_cache_compression
            and len(response) > settings.cache_compression_threshold
        ):
            try:
                compressed = gzip.compress(response.encode('utf-8'))
                answer_to_store = base64.b64encode(compressed).decode('ascii')
                metadata["compressed"] = True
                metadata["original_size"] = len(response)
                metadata["compressed_size"] = len(compressed)

                compression_ratio = len(compressed) / len(response)
                logger.debug(
                    f"Compressed answer: {len(response)} → {len(compressed)} bytes "
                    f"({compression_ratio * 100:.1f}% of original)"
                )
            except Exception as e:
                logger.warning(f"Compression failed: {e} - storing uncompressed")
                answer_to_store = response
                metadata["compressed"] = False
        else:
            answer_to_store = response
            metadata["compressed"] = False

        # ... store answer_to_store in Milvus ...

    def search_cache(self, ...) -> Optional[Dict]:
        """Search cache and decompress if needed."""
        # ... existing search logic ...

        cached_answer = best_match.get("text", "")
        metadata = best_match.get("metadata", {})

        # Decompress if needed
        if metadata.get("compressed", False):
            try:
                compressed_data = base64.b64decode(cached_answer)
                cached_answer = gzip.decompress(compressed_data).decode('utf-8')
                logger.debug(
                    f"Decompressed answer: {metadata.get('compressed_size')} → "
                    f"{len(cached_answer)} bytes"
                )
            except Exception as e:
                logger.error(f"Decompression failed: {e}")
                return None  # Invalidate corrupted cache entry

        return {
            "answer": cached_answer,
            "metadata": metadata,
            ...
        }
```

#### Configuration

```python
# In src/config/settings.py
class Settings(BaseSettings):
    # ... existing settings ...

    enable_cache_compression: bool = Field(
        default=False,
        validation_alias="ENABLE_CACHE_COMPRESSION",
    )
    cache_compression_threshold: int = Field(
        default=1000,
        validation_alias="CACHE_COMPRESSION_THRESHOLD",
    )
```

```bash
# Add to .env
ENABLE_CACHE_COMPRESSION=true
CACHE_COMPRESSION_THRESHOLD=1000  # Compress answers >1000 characters
```

#### When to Enable

- **Small deployments** (<1000 cached entries): Skip compression
- **Medium deployments** (1000-10,000 entries): Optional (test storage usage)
- **Large deployments** (>10,000 entries): Enable compression

---

## 💡 Long-Term Improvements

### 9. Auto-Identify Popular Questions (Smart Cache Warming)

**Current Problem**: Manual Q&A pair creation in `data/responses.json`
**Effort**: High | **Impact**: High | **Priority**: ⭐⭐

#### Expected Benefit
- Automated cache coverage optimization
- Focus cache on high-value questions
- Continuous improvement loop

#### Implementation

```python
# In src/tools/question_tracker.py (new file)
from collections import Counter
import json
from pathlib import Path

class QuestionTracker:
    """Track question frequency for cache optimization."""

    def __init__(self, log_file: str = "logs/question_frequency.json"):
        self.log_file = Path(log_file)
        self.counter = Counter()
        self._load_existing()

    def _load_existing(self):
        """Load existing frequency data."""
        if self.log_file.exists():
            with open(self.log_file, "r") as f:
                data = json.load(f)
                self.counter.update(data)

    def track(self, question: str):
        """Increment frequency counter for a question."""
        self.counter[question] += 1

    def save(self):
        """Persist frequency data to disk."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "w") as f:
            json.dump(dict(self.counter), f, indent=2)

    def get_popular(self, min_frequency: int = 5, limit: int = 50) -> List[Dict]:
        """Get frequently asked questions.

        Args:
            min_frequency: Minimum times a question was asked
            limit: Maximum number of questions to return

        Returns:
            List of {question, frequency} dictionaries
        """
        return [
            {"question": q, "frequency": count}
            for q, count in self.counter.most_common(limit)
            if count >= min_frequency
        ]
```

#### Integration

```python
# In api_server.py
from src.tools.question_tracker import QuestionTracker

# Global tracker
question_tracker = QuestionTracker()

@app.post("/v1/chat/completions")
async def chat_completions(...):
    # ... existing logic ...

    # Track question frequency
    question_tracker.track(question)

    # ... rest of logic ...

# Periodic save (every hour or on shutdown)
@app.on_event("shutdown")
async def save_question_frequency():
    question_tracker.save()
```

#### Workflow

**Weekly Process**:
1. Run for 1 week in production
2. Identify top 20-50 questions (`min_frequency >= 5`)
3. Generate answers for popular questions (manual or automated)
4. Add to `data/responses.json` for cache warmup
5. Deploy with updated cache
6. Monitor hit rate increase

**Automation Script**:
```bash
#!/bin/bash
# scripts/export_popular_questions.sh

python << EOF
from src.tools.question_tracker import QuestionTracker

tracker = QuestionTracker()
popular = tracker.get_popular(min_frequency=5, limit=20)

print(f"Found {len(popular)} popular questions:")
for item in popular:
    print(f"  [{item['frequency']}x] {item['question']}")

# Export to staging area
import json
with open("data/popular_questions.json", "w") as f:
    json.dump({"qa_pairs": [{"question": q["question"]} for q in popular]}, f, indent=2)

print("\nExported to data/popular_questions.json")
print("Next: Generate answers and merge into responses.json")
EOF
```

---

### 10. Add Cache Versioning

**Current Problem**: Can't invalidate cache when specific documentation updates
**Effort**: High | **Impact**: Medium | **Priority**: ⭐

#### Expected Benefit
- Selective cache invalidation
- Track which doc version answers came from
- Avoid full cache rebuild on doc updates

#### Implementation

```python
# In src/tools/response_cache.py
class MilvusResponseCache:
    def store_response(
        self,
        ...,
        doc_version: Optional[str] = None,
        doc_sections: Optional[List[str]] = None,
    ):
        """Store response with version tracking."""
        metadata.update({
            "doc_version": doc_version or "unknown",
            "doc_sections": doc_sections or [],  # e.g., ["installation", "api"]
            "invalidate_on_update": True,
        })
        # ... store in Milvus ...

    def invalidate_version(self, version: str) -> int:
        """Clear all cache entries for a specific document version.

        Args:
            version: Document version to invalidate (e.g., "v2.4.0")

        Returns:
            Number of entries invalidated
        """
        # Query all entries with this version
        filter_expr = f'metadata["doc_version"] == "{version}"'

        try:
            results = self.vector_db.client.query(
                collection_name=self.cache_collection_name,
                filter=filter_expr,
                output_fields=["id"],
                db_name=self.vector_db.db_name,
            )

            if not results:
                logger.info(f"No cache entries found for version {version}")
                return 0

            # Delete matching entries
            ids_to_delete = [r["id"] for r in results]
            self.vector_db.client.delete(
                collection_name=self.cache_collection_name,
                pks=ids_to_delete,
                db_name=self.vector_db.db_name,
            )

            logger.info(
                f"✓ Invalidated {len(ids_to_delete)} cache entries for version {version}"
            )
            return len(ids_to_delete)

        except Exception as e:
            logger.error(f"Failed to invalidate version {version}: {e}")
            return 0
```

#### Usage

```python
# When docs are updated
cache.invalidate_version("v2.4.0")  # Clear old version
# New answers will automatically use new version tag
```

#### API Endpoint

```python
# In api_server.py
@app.post("/api/cache/invalidate", tags=["cache"])
async def invalidate_cache_version(version: str):
    """Invalidate cached answers for a specific doc version."""
    agent = await get_or_init_agent()

    if not hasattr(agent, "response_cache") or not agent.response_cache:
        raise HTTPException(status_code=404, detail="Response cache not available")

    count = agent.response_cache.invalidate_version(version)

    return {
        "status": "success",
        "version": version,
        "invalidated_count": count,
    }
```

---

### 11. Multi-Source Cache Warmup

**Current Problem**: Only pre-loads from `data/responses.json`
**Effort**: Medium | **Impact**: Medium | **Priority**: ⭐⭐

#### Expected Benefit
- 50-100+ pre-warmed Q&A pairs (vs current 16)
- Better coverage of common topics
- Reduced cache misses in first deployment days

#### Implementation

```python
# In api_server.py - warm_response_cache() function
def warm_response_cache_multi_source(agent: StrandsGraphRAGAgent, settings) -> int:
    """Pre-warm cache from multiple sources.

    Returns:
        Total number of Q&A pairs loaded
    """
    sources = [
        ("data/responses.json", load_predefined_qa),
        ("data/popular_questions.json", load_popular_qa),
        ("data/topic_qa/milvus_basics.json", load_topic_qa),
        ("data/topic_qa/advanced_features.json", load_topic_qa),
        ("data/topic_qa/troubleshooting.json", load_topic_qa),
    ]

    total_loaded = 0

    for source_path, loader_func in sources:
        try:
            count = loader_func(source_path, agent, settings)
            total_loaded += count
            logger.info(f"✓ Loaded {count} Q&A pairs from {source_path}")
        except FileNotFoundError:
            logger.debug(f"Skipping {source_path} (file not found)")
        except Exception as e:
            logger.warning(f"Failed to load {source_path}: {e}")

    logger.info(f"✓ Total cache warmup: {total_loaded} Q&A pairs from {len(sources)} sources")
    return total_loaded


def load_predefined_qa(path: str, agent, settings) -> int:
    """Load manually curated Q&A pairs."""
    # ... existing responses.json loading logic ...
    return len(qa_pairs)


def load_popular_qa(path: str, agent, settings) -> int:
    """Load auto-identified popular questions."""
    with open(path, "r") as f:
        data = json.load(f)

    qa_pairs = data.get("qa_pairs", [])
    # Generate answers for questions that don't have them yet
    for qa in qa_pairs:
        if not qa.get("answer"):
            # Generate answer (you could automate this or keep manual)
            logger.debug(f"Skipping question without answer: {qa['question']}")
            continue
        # ... store in cache ...

    return len([qa for qa in qa_pairs if qa.get("answer")])


def load_topic_qa(path: str, agent, settings) -> int:
    """Load topic-specific Q&A sets."""
    # Similar to load_predefined_qa but from topic files
    # ... implementation ...
```

#### Directory Structure

```
data/
├── responses.json              # Manual high-quality Q&A (16 pairs)
├── popular_questions.json      # Auto-identified from logs (20-50 pairs)
└── topic_qa/
    ├── milvus_basics.json      # "What is Milvus?", "How to install?", etc.
    ├── advanced_features.json  # "How to tune HNSW?", "Partitioning?", etc.
    └── troubleshooting.json    # Common errors and solutions
```

#### Configuration

```bash
# Add to .env
CACHE_WARMUP_SOURCES=responses.json,popular_questions.json,topic_qa/*.json
```

---

## 📊 Recommended Configuration Updates

**Complete `.env` additions for all improvements:**

```bash
# ============================================================================
# Enhanced Caching Configuration (Improvements)
# ============================================================================

# -------- Layer 1: Embedding Cache (NEW) --------
ENABLE_EMBEDDING_CACHE=true

# -------- Layer 2: Search Cache (NEW) --------
ENABLE_SEARCH_CACHE=true

# -------- Cache Size Limits --------
# Applies to: embedding_cache, search_cache
# Already exists, now used by multiple caches
AGENT_CACHE_SIZE=500

# -------- Layer 3: Response Cache TTL (NEW) --------
RESPONSE_CACHE_TTL_HOURS=24  # Expire cached answers after 24 hours

# Environment-specific TTL values:
# Development:  1  # 1 hour for rapid iteration
# Staging:      6  # 6 hours for testing
# Production:  24  # 24 hours for stability

# -------- Negative Caching (NEW) --------
ENABLE_NEGATIVE_CACHE=true
NEGATIVE_CACHE_TTL_SECONDS=300  # Cache "no results" for 5 minutes

# -------- Similarity Threshold Tuning --------
RESPONSE_CACHE_THRESHOLD=0.95  # Lowered from 0.99
# Test values:
# 0.99 = Very strict (current baseline)
# 0.95 = Balanced (recommended)
# 0.92 = Looser (trial after 0.95)

# -------- Cache Compression (NEW) --------
ENABLE_CACHE_COMPRESSION=false  # Enable for large deployments (>10k entries)
CACHE_COMPRESSION_THRESHOLD=1000  # Compress answers >1000 chars

# -------- Cache Metrics (NEW) --------
ENABLE_CACHE_METRICS=true  # Track hit rates, misses, rejections

# -------- Cache Warmup Sources (NEW) --------
CACHE_WARMUP_SOURCES=responses.json,popular_questions.json,topic_qa/*.json
```

---

## 🎯 Implementation Roadmap

### Week 1: High-Priority Core Caching

**Focus**: Embedding and search caches + metrics

- [ ] **Day 1-2**: Implement embedding cache (#1)
  - Add `_get_cached_embedding()` method
  - Update all `embed_text()` calls
  - Add configuration flag
  - Write unit tests

- [ ] **Day 3**: Implement search cache (#2)
  - Add `retrieve_context_cached()` method
  - Update retrieval calls
  - Add configuration flag
  - Write unit tests

- [ ] **Day 4**: Add cache metrics (#4)
  - Add metrics tracking to `MilvusResponseCache`
  - Create `/health/detailed` endpoint
  - Test metrics collection
  - Document metrics in API docs

- [ ] **Day 5**: Testing & verification
  - Integration tests for all caches
  - Performance benchmarking
  - Load testing with concurrent requests
  - Document performance improvements

**Expected Results**:
- ✅ 256ms savings per cached embedding
- ✅ 10-30ms savings per cached search
- ✅ Real-time metrics via `/health/detailed`

---

### Week 2: TTL and Threshold Optimization

**Focus**: Cache freshness and hit rate tuning

- [ ] **Day 1-2**: Implement cache TTL (#3)
  - Add TTL logic to `store_response()`
  - Add TTL validation in `search_cache()`
  - Add configuration settings
  - Test with various TTL values

- [ ] **Day 3**: Enable `agent_cache_size` (#5)
  - Verify setting is used by new caches
  - Update documentation
  - Clean up misleading comments

- [ ] **Day 4**: Lower similarity threshold (#7)
  - Change from 0.99 to 0.95
  - Monitor hit rate for 24 hours
  - Check for false positives
  - Document findings

- [ ] **Day 5**: Analysis & tuning
  - Compare hit rates: 0.99 vs 0.95
  - Review accuracy (sample 20 cached answers)
  - Decide on final threshold
  - Update documentation with recommendation

**Expected Results**:
- ✅ Automatic cache expiration (24h TTL)
- ✅ 20-30% higher hit rate with 0.95 threshold
- ✅ No stale answers after doc updates

---

### Week 3: Negative Caching and Compression

**Focus**: Edge cases and storage optimization

- [ ] **Day 1-2**: Implement negative caching (#6)
  - Add negative cache data structure
  - Add negative caching logic
  - Add configuration settings
  - Test with unanswerable questions

- [ ] **Day 3-4**: Implement cache compression (#8)
  - Add compression/decompression logic
  - Add configuration settings
  - Test with large answers (>1000 chars)
  - Benchmark compression overhead

- [ ] **Day 5**: Performance benchmarking
  - Test all caches together
  - Measure end-to-end latency improvements
  - Document performance gains
  - Create performance comparison report

**Expected Results**:
- ✅ Faster failures for unanswerable questions
- ✅ 60-80% storage reduction (if compression enabled)
- ✅ Combined 300-400ms average speedup

---

### Week 4+: Long-Term Features

**Focus**: Automation and advanced features

- [ ] **Week 4**: Question tracking and analytics (#9)
  - Implement `QuestionTracker` class
  - Integrate with API server
  - Run for 1 week to collect data
  - Export popular questions

- [ ] **Week 5**: Generate answers for popular questions
  - Review top 20 questions
  - Generate high-quality answers
  - Add to `data/popular_questions.json`
  - Deploy with updated cache

- [ ] **Week 6**: Cache versioning (#10)
  - Add version metadata to cache entries
  - Implement `invalidate_version()` method
  - Create API endpoint
  - Test selective invalidation

- [ ] **Week 7**: Multi-source cache warmup (#11)
  - Create topic Q&A files
  - Implement multi-source loader
  - Test warmup from all sources
  - Document maintenance procedures

**Expected Results**:
- ✅ Automated popular question identification
- ✅ 50-100+ pre-warmed Q&A pairs
- ✅ Selective cache invalidation on doc updates

---

## 📈 Expected Performance Impact

### Summary Table

| Improvement | Latency Savings | Storage Impact | Throughput Impact | Effort | Priority |
|-------------|----------------|----------------|-------------------|--------|----------|
| **Embedding Cache** | ~256ms/query | In-memory (~50MB) | -40-60% Ollama calls | Low | ⭐⭐⭐ HIGH |
| **Search Cache** | ~10-30ms/query | In-memory (~20MB) | -30-50% Milvus queries | Low | ⭐⭐ MEDIUM |
| **Cache TTL** | Prevents stale | None | Slight increase (refresh) | Medium | ⭐⭐⭐ HIGH |
| **Cache Metrics** | Enables tuning | Minimal (<1MB) | None | Low | ⭐⭐⭐ HIGH |
| **Use agent_cache_size** | None | None | None | Trivial | ⭐⭐ MEDIUM |
| **Optimize Threshold** | +20-40% hit rate | None | Same | Trivial | ⭐⭐ MEDIUM |
| **Negative Caching** | Avoids wasted searches | In-memory (<1MB) | -10-20% failed searches | Low | ⭐⭐ MEDIUM |
| **Cache Compression** | <1ms overhead | -60-80% storage | None | Medium | ⭐ LOW |
| **Smart Warmup** | Better coverage | None | More hits | High | ⭐⭐ MEDIUM |
| **Cache Versioning** | Selective refresh | Metadata (<5MB) | Targeted refresh | High | ⭐ LOW |
| **Multi-Source Warmup** | 50-100+ hits | +100KB storage | More hits | Medium | ⭐⭐ MEDIUM |

### Combined Impact

**With all High-Priority improvements** (#1-4):
- **Average speedup**: 300-400ms for cached questions
- **Hit rate increase**: 40-60% (with threshold tuning)
- **Ollama load reduction**: 40-60%
- **Milvus load reduction**: 30-50%
- **Memory overhead**: ~70-100MB (acceptable)

**Full implementation** (all 11 improvements):
- **Average speedup**: 350-500ms for cached questions
- **Hit rate**: 60-80% (with good cache warmup)
- **Storage efficiency**: 60-80% reduction (with compression)
- **Automation**: Auto-identify popular questions
- **Freshness**: Automatic refresh with TTL + versioning

---

## 🔧 Monitoring and Tuning

### Key Metrics to Track

**1. Cache Hit Rates**
- **Response Cache**: Target >50% after warmup
- **Embedding Cache**: Target >60% (questions repeat more)
- **Search Cache**: Target >50% (similar to response)

**2. Latency Distribution**
- **Cache hit**: <50ms (Tier 1)
- **KB search**: 1-2s (Tier 2)
- **Web search**: 5-15s (Tier 3)

**3. Cache Health**
- **Entity Rejection Rate**: Should be <5%
- **TTL Expiration Rate**: Monitor for doc update patterns
- **Negative Cache Usage**: Track avoided searches

**4. Storage Growth**
- Monitor cache collection size over time
- Set alerts for rapid growth (>10% per day)
- Plan for cache size limits or LRU

### Health Check Queries

```bash
# Basic health check
curl http://localhost:8000/health | jq '.'

# Detailed cache metrics
curl http://localhost:8000/health/detailed | jq '.cache_metrics'

# Expected output after improvements:
{
  "embedding_cache": {
    "enabled": true,
    "size": 245,
    "max_size": 500,
    "hit_rate_estimate": "~60%"
  },
  "search_cache": {
    "enabled": true,
    "size": 189,
    "max_size": 500,
    "hit_rate_estimate": "~50%"
  },
  "response_cache": {
    "hit_rate": 0.68,
    "hit_rate_percent": "68.0%",
    "hits": 340,
    "misses": 160,
    "entity_rejections": 12,
    "ttl_expirations": 8,
    "total_searches": 500,
    "cache_size": 156
  }
}
```

### Performance Benchmarking

```bash
# Run benchmark suite
python scripts/benchmark_caching.py

# Example output:
========================================
Cache Performance Benchmark
========================================
Test 1: Fresh question (all caches cold)
  Latency: 1842ms
  Path: KB search + LLM generation

Test 2: Exact repeat (embedding + search + response cache hit)
  Latency: 38ms (48x faster!)
  Path: Response cache

Test 3: Similar question (semantic cache hit)
  Latency: 42ms (44x faster!)
  Path: Response cache (95.2% similar)

Test 4: Different phrasing (embedding cache hit)
  Latency: 1624ms (embedding saved 256ms)
  Path: KB search + LLM generation

Test 5: Unanswerable question (negative cache)
  First attempt: 185ms (search returned empty)
  Second attempt: 2ms (negative cache hit)
========================================
Average speedup: 42x for cached questions
Cache hit rate: 68%
========================================
```

### Tuning Guidelines

**If hit rate is low (<40%)**:
- ✅ Lower similarity threshold (try 0.92)
- ✅ Increase cache warmup coverage
- ✅ Review entity rejection rate
- ✅ Check TTL isn't too aggressive

**If seeing false positives (wrong answers)**:
- ✅ Raise similarity threshold (back to 0.99)
- ✅ Review entity validation logic
- ✅ Add more entities to validation list
- ✅ Consider manual review of top 20 cached answers

**If storage growing too fast**:
- ✅ Enable cache compression
- ✅ Implement LRU eviction for response cache
- ✅ Lower TTL to expire faster
- ✅ Set max cache size limit

**If cache feels "stale"**:
- ✅ Lower TTL (try 12h or 6h)
- ✅ Implement cache versioning
- ✅ Manual invalidation on doc updates

---

## 📝 Migration Notes

### Backward Compatibility

All improvements are **backward compatible**:
- Existing response cache continues to work
- New caches are additive (opt-in via flags)
- Configuration changes are optional
- No breaking changes to API

### Gradual Rollout

**Recommended approach**:
1. **Week 1**: Deploy embedding + search caches (low risk)
2. **Week 2**: Enable TTL + metrics (medium risk)
3. **Week 3**: Lower threshold after monitoring (test first)
4. **Week 4+**: Add compression + advanced features (optional)

### Rollback Strategy

**If issues arise**:
```bash
# Disable all new features
ENABLE_EMBEDDING_CACHE=false
ENABLE_SEARCH_CACHE=false
ENABLE_NEGATIVE_CACHE=false
ENABLE_CACHE_COMPRESSION=false
RESPONSE_CACHE_THRESHOLD=0.99  # Revert to strict

# Restart API server
pkill -f api_server.py
python api_server.py
```

---

## ✅ Success Criteria

### Short-Term (Week 1-3)

- [ ] Embedding cache implemented and tested
- [ ] Search cache implemented and tested
- [ ] Cache metrics visible in `/health/detailed`
- [ ] TTL working correctly (entries expire after 24h)
- [ ] Hit rate increased by 20-30% (threshold tuning)
- [ ] No increase in false positives
- [ ] Performance improvement documented

### Long-Term (Month 1-3)

- [ ] Cache hit rate >60%
- [ ] Average cached query latency <50ms
- [ ] Question tracking collecting data
- [ ] Popular questions auto-identified
- [ ] Multi-source cache warmup deployed
- [ ] Cache versioning operational
- [ ] Zero stale answer complaints

---

## 📚 Related Documentation

- [CACHING_STRATEGY.md](CACHING_STRATEGY.md) - Current caching implementation
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Full system architecture
- [LATENCY_OPTIMIZATION.md](LATENCY_OPTIMIZATION.md) - Performance tuning guide
- [API_SERVER.md](API_SERVER.md) - API endpoints and caching behavior
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development guide

---

**Document Status**: Ready for implementation
**Approval Required**: Yes (review before Week 1 implementation)
**Estimated Total Effort**: 4-6 weeks for full implementation
**Expected ROI**: 40-60% latency reduction, 60-80% higher hit rate
