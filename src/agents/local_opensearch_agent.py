"""Local-Mode agent facade backed by OpenSearch (Phase 1 of the migration).

When ``DEPLOYMENT_MODE=local`` (and ``LOCAL_VECTOR_BACKEND=opensearch``, the only
supported local engine), ``api_server.py`` uses this facade as the local-mode
agent. It exposes the same method surface the chat endpoints call, but delegates
answering to the backend-agnostic ``shared_route`` built by
:func:`create_rag_graph` — the SAME pipeline the serverless Lambda uses — wired
with Ollama + local OpenSearch (+ optional local Redis). This mirrors the proven
``ServerlessAgentShim`` in ``scripts/serverless_api_server.py`` but with local
Ollama backends.

Design notes:
- No Bedrock, no AWS. Embeddings + generation are Ollama; retrieval + Layer 4
  cache are the local OpenSearch container; Layer 2/3 is InMemory or local Redis
  per ``REDIS_CACHE_ENABLED`` (both resolved inside ``create_rag_graph``).
- Retrieval goes through ``VectorStore.knn_search`` (the protocol path), so this
  facade is byte-compatible with the serverless answer path.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["LocalOpenSearchAgent"]


class _OpenSearchCacheQueryClient:
    """``client``-shaped shim exposing ``query(...)`` over rag-cache.

    GET /v1/cache/responses/{id} calls
    ``vector_db.client.query(collection_name=..., db_name=..., output_fields=...,
    limit=...)`` expecting ``{"id","text","metadata"}`` entities. Maps the
    OpenSearch ``rag-cache`` docs (``question``/``answer``/``sources``) into that
    shape so the cache endpoint works unchanged.
    """

    def __init__(self, opensearch_client: Any) -> None:
        self._os = opensearch_client

    def query(  # noqa: ANN201
        self,
        collection_name: str | None = None,  # noqa: ARG002
        db_name: str | None = None,  # noqa: ARG002
        output_fields: list[str] | None = None,  # noqa: ARG002
        limit: int = 100,
        **_kw: Any,
    ):
        try:
            body = {"size": limit, "query": {"match_all": {}}}
            resp = self._os.client.search(index=self._os.cache_index, body=body)
            hits = (resp or {}).get("hits", {}).get("hits", [])
        except Exception as exc:  # noqa: BLE001 - endpoint degrades to empty
            logger.warning("rag-cache query failed: %s", exc)
            return []

        entities = []
        for hit in hits:
            src = hit.get("_source", {}) or {}
            entities.append(
                {
                    "id": str(hit.get("_id", "")),
                    "text": src.get("answer", ""),
                    "metadata": {
                        "sources": src.get("sources", []),
                        "question": src.get("question", ""),
                    },
                }
            )
        return entities


class _OpenSearchQuestionLister:
    """``vector_db``-shaped object for the cached-questions/response endpoints."""

    def __init__(self, opensearch_client: Any) -> None:
        self._os = opensearch_client
        self.client = _OpenSearchCacheQueryClient(opensearch_client)
        self.db_name = "local-opensearch"  # unused by OpenSearch; parity only

    def list_all_cached_questions(self, collection_name: str, limit: int = 100):  # noqa: ANN201, ARG002
        try:
            body = {
                "size": limit,
                "_source": ["question", "created_at"],
                "sort": [{"created_at": {"order": "desc"}}],
                "query": {"match_all": {}},
            }
            resp = self._os.client.search(index=self._os.cache_index, body=body)
            hits = (resp or {}).get("hits", {}).get("hits", [])
        except Exception as exc:  # noqa: BLE001 - endpoint degrades to empty
            logger.warning("Listing cached questions failed: %s", exc)
            return []

        seen: set[str] = set()
        questions: list[dict] = []
        for hit in hits:
            q = (hit.get("_source", {}) or {}).get("question", "")
            if q and q not in seen:
                seen.add(q)
                questions.append({"id": str(hit.get("_id", "")), "question": q})
        return questions


class _OpenSearchResponseCacheAdapter:
    """Response-cache adapter backing the cached-questions endpoints."""

    def __init__(self, opensearch_client: Any, settings: Settings) -> None:
        self.vector_db = _OpenSearchQuestionLister(opensearch_client)
        self.cache_collection_name = settings.opensearch_cache_index


class LocalOpenSearchAgent:
    """Local-Mode agent facade delegating to the shared OpenSearch pipeline.

    Duck-typed drop-in for :class:`StrandsGraphRAGAgent`: exposes the method
    surface the FastAPI chat endpoints call. Answering delegates to the graph's
    ``shared_route``, so this is the real backend-agnostic Cache → KB → Web
    pipeline with Ollama + local OpenSearch, not a reimplementation.
    """

    def __init__(self, settings: Settings) -> None:
        from src.agents.strands_graph_agent import create_rag_graph
        from src.tools.opensearch_client import OpenSearchClient

        self.settings = settings
        self.initialization_error: str | None = None
        self._last_stream_sources: list[dict] = []

        # Build the local OpenSearch client up front so we can ensure indexes and
        # expose it for health/cache listing. create_rag_graph will reuse it.
        try:
            self._opensearch = OpenSearchClient.for_local(settings)
            self._opensearch.ensure_indexes()
        except Exception as exc:  # noqa: BLE001 - degrade on connect failure
            self._opensearch = None  # type: ignore[assignment]
            self.initialization_error = f"OpenSearch connection failed: {exc}"
            logger.warning("Local OpenSearch unavailable, degraded mode: %s", exc)

        self._graph = create_rag_graph(settings, opensearch_client=self._opensearch)
        self._shared_route = self._graph["shared_route"]
        backends = self._graph.get("backends", {})
        self.web_search = backends.get("web_search")
        # Ollama client (the graph's LLM backend) for the MCP-skill primitives
        # (embed/generate) so this facade can back the MCP server too.
        self.ollama_client = backends.get("llm")
        self._kb_index = self._graph.get("kb_index", settings.opensearch_kb_index)

        # ``vector_db`` attribute for parity with StrandsGraphRAGAgent (some
        # endpoints read it); points at the OpenSearch client.
        self.vector_db = self._opensearch

    # ------------------------------------------------------------------ #
    # Health                                                             #
    # ------------------------------------------------------------------ #
    def opensearch_healthy(self) -> bool:
        """Return True when the local OpenSearch backend responds."""
        if self._opensearch is None:
            return False
        try:
            return bool(self._opensearch.client.ping())
        except Exception as exc:  # noqa: BLE001 - report unhealthy, don't raise
            logger.warning("OpenSearch health check failed: %s", exc)
            return False

    @property
    def response_cache(self) -> _OpenSearchResponseCacheAdapter | None:
        """Cached-questions listing adapter (GET /v1/cache/questions)."""
        if self._opensearch is None:
            return None
        return _OpenSearchResponseCacheAdapter(self._opensearch, self.settings)

    # ------------------------------------------------------------------ #
    # Answering (delegates to shared_route)                              #
    # ------------------------------------------------------------------ #
    def _run(
        self,
        question: str,
        top_k: int,
        temperature: float | None,
        max_tokens: int | None,
    ) -> Any:
        return self._shared_route(
            question,
            top_k=top_k,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def answer_question(
        self,
        collection_name: str = "",  # noqa: ARG002 - OpenSearch index from settings
        question: str = "",
        top_k: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **_kwargs: Any,
    ) -> dict:
        result = self._run(question, top_k, temperature, max_tokens)
        return {"answer": result.answer, "sources": result.sources}

    async def answer_question_no_cache(
        self,
        collection_name: str = "",  # noqa: ARG002
        question: str = "",
        top_k: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **_kwargs: Any,
    ) -> tuple[str, list[dict]]:
        result = self._run(question, top_k, temperature, max_tokens)
        return result.answer, result.sources

    async def stream_answer(
        self,
        collection_name: str = "",  # noqa: ARG002
        question: str = "",
        top_k: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **_kwargs: Any,
    ):  # noqa: ANN201
        result = self._run(question, top_k, temperature, max_tokens)
        sources = list(result.sources)
        if result.cache_hit:
            for s in sources:
                s.setdefault("source_type", "cached")
        self._last_stream_sources = sources
        yield result.answer

    async def stream_answer_no_cache(
        self,
        collection_name: str = "",  # noqa: ARG002
        question: str = "",
        top_k: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **_kwargs: Any,
    ):  # noqa: ANN201
        result = self._run(question, top_k, temperature, max_tokens)
        self._last_stream_sources = list(result.sources)
        yield result.answer

    def _generate_web_search_query(self, question: str) -> str:
        return question

    async def stream_answer_web_search_only(
        self,
        question: str,
        temperature: float | None = None,  # noqa: ARG002
        max_tokens: int | None = None,  # noqa: ARG002
        **_kwargs: Any,
    ):  # noqa: ANN201
        """Force-web path. Delegates to the graph's force_web_search route."""
        self._last_stream_sources = []
        if self.web_search is None:
            yield (
                "Web search is not enabled. Set ENABLE_WEB_SEARCH_SUPPLEMENT=true "
                "and TAVILY_API_KEY, then restart."
            )
            return
        result = self._shared_route(question, force_web_search=True)
        self._last_stream_sources = list(result.sources)
        yield result.answer

    def answer_question_web_search_only(
        self,
        question: str,
        temperature: float | None = None,  # noqa: ARG002
        max_tokens: int | None = None,  # noqa: ARG002
    ) -> tuple[str, list[dict]]:
        """Sync force-web answer (non-streaming chat path). Returns (answer, sources)."""
        if self.web_search is None:
            return (
                "Web search is not enabled. Set ENABLE_WEB_SEARCH_SUPPLEMENT=true "
                "and TAVILY_API_KEY, then restart.",
                [],
            )
        result = self._shared_route(question, force_web_search=True)
        return result.answer, list(result.sources)

    # ------------------------------------------------------------------ #
    # MCP-skill primitives (backend-agnostic, via OpenSearch + Ollama)   #
    # ------------------------------------------------------------------ #
    # These back the MCP server's retrieval/answer/KB skills. They operate
    # through the OpenSearch VectorStore contract and the Ollama client. When
    # OpenSearch is unavailable they degrade to empty/no-op.

    def retrieve_context(
        self, collection_name: str, query: str, top_k: int = 5
    ) -> tuple[list[str], list[dict]]:
        """Embed ``query`` with Ollama and k-NN search OpenSearch.

        Returns ``(context_chunks, sources)``. ``collection_name`` is accepted
        for interface parity but OpenSearch Local Mode uses the configured KB
        index. Degrades to empty on any failure.
        """
        if self._opensearch is None or self.ollama_client is None:
            return [], []
        try:
            vector = self.ollama_client.embed_text(query, model=self.settings.ollama_embed_model)
            results = self._opensearch.knn_search(self._kb_index, vector, top_k)
        except Exception as exc:  # noqa: BLE001 - degrade to empty
            logger.warning("retrieve_context failed: %s", exc)
            return [], []

        chunks: list[str] = []
        sources: list[dict] = []
        for r in results:
            text = r.get("text", "")
            metadata = r.get("metadata", {}) or {}
            chunks.append(text)
            sources.append(
                {
                    "source_type": "knowledge_base",
                    "id": r.get("id"),
                    "text": text[:200],
                    "document_name": metadata.get("document_name", ""),
                    "metadata": metadata,
                    "distance": r.get("distance", 0.0),
                    "collection": self._kb_index,
                }
            )
        return chunks, sources

    def retrieve_documents(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        filter_source: str | None = None,
    ) -> list[dict]:
        """MCP retrieval tool: return source docs, optionally filtered by source."""
        _, sources = self.retrieve_context(collection_name, query, top_k)
        if filter_source:
            sources = [d for d in sources if d.get("metadata", {}).get("source") == filter_source]
        return sources

    def search_by_source(
        self, collection_name: str, query: str, source: str, top_k: int = 5
    ) -> list[dict]:
        """MCP retrieval tool: search filtered by a specific source."""
        return self.retrieve_documents(collection_name, query, top_k, filter_source=source)

    def list_collections(self) -> list[str]:
        """MCP retrieval tool: list OpenSearch KB/cache index names present."""
        if self._opensearch is None:
            return []
        names = [self.settings.opensearch_kb_index, self.settings.opensearch_cache_index]
        try:
            return [n for n in names if self._opensearch.client.indices.exists(index=n)]
        except Exception as exc:  # noqa: BLE001 - degrade to empty
            logger.warning("list_collections failed: %s", exc)
            return []

    def generate_answer(
        self,
        question: str,
        context: str,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> str:
        """MCP answer-generation tool: generate from context via Ollama."""
        if self.ollama_client is None:
            return "Generation backend unavailable."
        from src.agents import prompts

        system_instructions = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
            formatting_rules=prompts.FORMATTING_RULES
        )
        prompt = prompts.format_rag_prompt(
            system_instructions=system_instructions, question=question, context=context
        )
        try:
            answer = self.ollama_client.generate(
                prompt=prompt,
                model=self.settings.ollama_model,
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else self.settings.max_tokens,
            )
            return str(answer)
        except Exception as exc:  # noqa: BLE001
            logger.error("generate_answer failed: %s", exc)
            return f"Error generating answer: {exc}"

    def add_documents(self, collection_name: str, documents: list[dict]) -> dict:
        """MCP knowledge-base tool: embed + index documents into OpenSearch.

        Each document is ``{text, source?, metadata?}``. Returns a result dict.
        """
        if self._opensearch is None or self.ollama_client is None:
            return {"success": False, "message": "OpenSearch/Ollama unavailable", "count": 0}
        indexed = 0
        try:
            for i, doc in enumerate(documents):
                text = doc.get("text", "")
                if not text.strip():
                    continue
                vector = self.ollama_client.embed_text(text, model=self.settings.ollama_embed_model)
                self._opensearch.index_document(
                    index=self.settings.opensearch_kb_index,
                    doc_id=doc.get("id") or f"mcp-{i}",
                    vector=vector,
                    text=text,
                    metadata={"source": doc.get("source", "mcp"), **(doc.get("metadata") or {})},
                )
                indexed += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("add_documents failed after %d: %s", indexed, exc)
            return {"success": False, "message": str(exc), "count": indexed}
        return {"success": True, "message": f"Indexed {indexed} document(s)", "count": indexed}
