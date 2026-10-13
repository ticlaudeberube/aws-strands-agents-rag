#!/usr/bin/env python
"""FastAPI server running the SERVERLESS pipeline locally, for the GUI (Option 1).

Reuses the existing OpenAI-compatible FastAPI ``app`` (and all its routes) from
``api_server.py`` but swaps the Local-Mode agent for a thin serverless-backed
shim. The shim exposes the same interface the chat endpoint calls
(``answer_question`` / ``answer_question_no_cache`` / ``web_search`` /
``stream_answer_web_search_only``) and delegates answering to the serverless
``shared_route`` from ``create_rag_graph`` — the exact Lambda code path — backed
by REAL Bedrock + LOCAL OpenSearch/Redis containers.

No edits are made to ``api_server.py`` or ``src/``. This server simply:
    1. loads .env.serverless-local,
    2. builds injected serverless backends (Bedrock + local OpenSearch/Redis),
    3. seeds a couple of KB docs so retrieval returns context,
    4. sets the api_server module globals to our shim,
    5. runs uvicorn on the shared app.

Run:
    .venv/bin/python scripts/serverless_api_server.py
Then point the React app at http://localhost:8000 (its default) and chat.

Prereqs: docker/serverless-local/docker-compose.yml up; AWS creds for
996428372683 in us-east-1.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the repo root is importable regardless of how this script is launched
# (e.g. `python scripts/serverless_api_server.py` from the repo root), so the
# `scripts.*`, `api_server`, and `src.*` imports below resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env.serverless-local", override=True)
except Exception:  # noqa: BLE001
    pass

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("serverless_api_server")

# Reuse the local-run helpers (local OpenSearch/Redis client construction + seed).
from scripts.run_serverless_local import (  # noqa: E402
    build_local_dynamodb_client,
    build_local_opensearch_client,
    build_local_redis_cache,
    seed_knowledge_base,
)


class _OpenSearchCacheQueryClient:
    """Milvus-``client``-shaped shim exposing ``query(...)`` over rag-cache.

    The GUI's GET /v1/cache/responses/{id} endpoint calls
    ``vector_db.client.query(collection_name=..., db_name=..., output_fields=...,
    limit=...)`` and expects entities shaped ``{"id","text","metadata"}`` where
    ``text`` is the answer and ``metadata.sources`` the source list. This maps
    the OpenSearch ``rag-cache`` docs (fields ``question``/``answer``/``sources``)
    into that shape so a Milvus-oriented endpoint works unchanged.
    """

    def __init__(self, opensearch_client):
        self._os = opensearch_client

    def query(self, collection_name=None, db_name=None, output_fields=None, limit=100, **_kw):  # noqa: ANN001, ARG002
        try:
            body = {"size": limit, "query": {"match_all": {}}}
            resp = self._os.client.search(index=self._os.cache_index, body=body)
            hits = (resp or {}).get("hits", {}).get("hits", [])
        except Exception as exc:  # noqa: BLE001
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
    """``vector_db``-shaped object for the cached-questions/response endpoints.

    Exposes ``list_all_cached_questions(...)`` (for GET /v1/cache/questions) and
    a Milvus-like ``client.query(...)`` + ``db_name`` (for GET
    /v1/cache/responses/{id}), both backed by the OpenSearch ``rag-cache`` index.
    """

    def __init__(self, opensearch_client):
        self._os = opensearch_client
        self.client = _OpenSearchCacheQueryClient(opensearch_client)
        self.db_name = "serverless"  # unused by OpenSearch; present for parity

    def list_all_cached_questions(self, collection_name: str, limit: int = 100):  # noqa: ARG002
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
    """Stands in for MilvusResponseCache for the cached-questions endpoints."""

    def __init__(self, opensearch_client, settings):
        self.vector_db = _OpenSearchQuestionLister(opensearch_client)
        self.cache_collection_name = settings.opensearch_cache_index


class ServerlessAgentShim:
    """Adapter matching the subset of StrandsGraphRAGAgent the GUI calls.

    The chat endpoint (api_server.chat_completions) uses:
      * ``await answer_question(collection_name, question, top_k, temperature,
        max_tokens)`` -> dict {"answer","sources"} or (answer, sources)
      * ``await answer_question_no_cache(...)`` (bypass_cache path)
      * ``web_search`` attribute (force-web path; None disables it)
      * ``stream_answer_web_search_only(...)`` / ``_generate_web_search_query``
        / ``_last_stream_sources`` (force-web path only)
      * ``initialization_error`` attribute

    Answering delegates to the serverless ``shared_route`` so this is the real
    serverless Cache -> KB -> (Web) pipeline, not a reimplementation.
    """

    def __init__(self, settings):
        from src.agents.strands_graph_agent import create_rag_graph
        from src.tools.bedrock_client import BedrockClient

        self.settings = settings
        self.initialization_error: str | None = None
        self._last_stream_sources: list[dict] = []

        # Injected serverless backends: real Bedrock, local OpenSearch, local
        # Redis, local DynamoDB (session history, matching the Lambda handler).
        self._bedrock = BedrockClient(settings)
        self._opensearch = build_local_opensearch_client()
        self._redis = build_local_redis_cache(settings)
        self._ddb = build_local_dynamodb_client(settings)

        # Ensure indexes + seed KB so GUI queries retrieve real context.
        self._opensearch.ensure_indexes()
        seeded = seed_knowledge_base(self._opensearch, self._bedrock, settings.opensearch_kb_index)
        logger.info("Seeded %d KB document(s) into %s", seeded, settings.opensearch_kb_index)

        self._graph = create_rag_graph(
            settings,
            bedrock_client=self._bedrock,
            opensearch_client=self._opensearch,
            redis_cache=self._redis,
        )
        self._shared_route = self._graph["shared_route"]

        # Web search follows the graph's configuration (disabled unless enabled
        # via ENABLE_WEB_SEARCH_SUPPLEMENT + a Tavily key).
        self.web_search = self._graph.get("backends", {}).get("web_search")

    @property
    def response_cache(self):
        """Adapter exposing the cached-questions listing the GUI expects.

        The React app's questions list calls GET /v1/cache/questions, which does
        ``agent.response_cache.vector_db.list_all_cached_questions(
        collection_name=response_cache.cache_collection_name, limit=...)``. In
        serverless mode the L4 cache lives in the OpenSearch ``rag-cache`` index,
        so this adapter lists the questions stored there, matching the
        ``[{"id","question"}]`` shape the endpoint returns.
        """
        return _OpenSearchResponseCacheAdapter(self._opensearch, self.settings)

    def opensearch_healthy(self) -> bool:
        """Return True when the local OpenSearch backend responds.

        Used by the serverless-aware /health override. The default api_server
        /health probes a Milvus vector_db that this shim doesn't have, which is
        why it must be overridden for serverless-local use.
        """
        try:
            return bool(self._opensearch.client.ping())
        except Exception as exc:  # noqa: BLE001 - report unhealthy, don't raise
            logger.warning("OpenSearch health check failed: %s", exc)
            return False

    def redis_healthy(self) -> bool:
        """Return True when the local Redis cache responds (best-effort)."""
        try:
            return bool(self._redis.ping())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # DynamoDB session history (mirrors agentcore_handler load/persist)   #
    # ------------------------------------------------------------------ #
    def _load_history(self, session_id: str) -> list[dict]:
        """Load session history, degrading to empty on failure (like the Lambda)."""
        if self._ddb is None or not session_id:
            return []
        try:
            from src.tools.dynamodb_client import SessionReadError

            return self._ddb.load_history(session_id)
        except SessionReadError:
            logger.warning("Session read failed for %s; using empty history.", session_id)
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("Session read error for %s: %s", session_id, exc)
            return []

    def _persist_turn(self, session_id: str, question: str, answer: str) -> None:
        """Persist a Q/A turn, swallowing write failures (like the Lambda)."""
        if self._ddb is None or not session_id:
            return
        try:
            self._ddb.persist_turn(session_id, question, answer)
        except Exception as exc:  # noqa: BLE001 - persistence must not break the answer
            logger.warning("Session persist failed for %s: %s", session_id, exc)

    def _run(self, question: str, top_k, temperature, max_tokens, session_id: str = ""):
        """Load history → shared_route → persist turn. The session-aware core
        shared by all answer paths, matching the Lambda handler's sequence."""
        history = self._load_history(session_id)
        logger.info("Loaded %d history turn(s) for session %s", len(history), session_id or "-")
        result = self._shared_route(
            question,
            top_k=top_k,
            temperature=temperature,
            max_tokens=max_tokens,
            history=history,
        )
        self._persist_turn(session_id, question, result.answer)
        return result

    async def answer_question(
        self,
        collection_name: str = "",  # noqa: ARG002 - serverless uses OpenSearch index from settings
        question: str = "",
        top_k: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        session_id: str = "",
    ) -> dict:
        """Answer via the serverless shared route; returns {'answer','sources'}."""
        result = self._run(question, top_k, temperature, max_tokens, session_id)
        return {"answer": result.answer, "sources": result.sources}

    async def answer_question_no_cache(
        self,
        collection_name: str = "",  # noqa: ARG002
        question: str = "",
        top_k: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        session_id: str = "",
    ) -> tuple[str, list[dict]]:
        """Bypass-cache path. The serverless route always consults the semantic
        cache first; for a local GUI test this distinction is immaterial, so we
        reuse the same route and return the (answer, sources) tuple form."""
        result = self._run(question, top_k, temperature, max_tokens, session_id)
        return result.answer, result.sources

    async def stream_answer(
        self,
        collection_name: str = "",  # noqa: ARG002
        question: str = "",
        top_k: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        session_id: str = "",
    ):
        """Streaming (SSE) path used by the GUI's default request.

        Bedrock generation here is synchronous (not token-streaming), so the
        serverless shared route is run once and the full answer is yielded as a
        single chunk. ``_last_stream_sources`` is populated so the endpoint can
        emit the sources/response_type trailer after the text. Session history
        is loaded/persisted via DynamoDB, matching the Lambda handler.
        """
        result = self._run(question, top_k, temperature, max_tokens, session_id)
        # Tag sources so the endpoint's response_type logic (cached/web/rag)
        # classifies this correctly.
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
        session_id: str = "",
    ):
        """Bypass-cache streaming path; same route (see answer_question_no_cache)."""
        result = self._run(question, top_k, temperature, max_tokens, session_id)
        self._last_stream_sources = list(result.sources)
        yield result.answer

    def _generate_web_search_query(self, question: str) -> str:
        """Pass the question through as the web search query."""
        return question

    async def stream_answer_web_search_only(
        self,
        question: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **_kwargs,
    ):
        """Force-web-search path: answer from Tavily results only (no KB).

        Runs a real web search via the injected WebSearchClient, formats the
        results into web sources (matching the app's ``source_type:web_search``
        schema), asks Bedrock to answer from them, and yields the answer. If web
        search is unavailable (no key / API down / no results), yields an
        informative message instead.
        """
        self._last_stream_sources = []

        if self.web_search is None:
            yield (
                "Web search is not enabled in this local serverless setup. Set "
                "ENABLE_WEB_SEARCH_SUPPLEMENT=true and TAVILY_API_KEY in "
                ".env.serverless-local, then restart the server."
            )
            return

        try:
            results, status = self.web_search.search(query=question, max_results=5)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("Force web search failed: %s", exc)
            results, status = [], "api_unavailable"

        if status != "success" or not results:
            yield (
                "Web search returned no usable results "
                f"(status: {status}). Try rephrasing your question."
            )
            return

        web_sources = [
            {
                "source_type": "web_search",
                "url": item.get("url", ""),
                "title": item.get("title", "Web Result"),
                "text": item.get("snippet", ""),
                "snippet": item.get("snippet", ""),
                "distance": 0.7,
                "metadata": {"source": "web", "title": item.get("title", "")},
            }
            for item in results
        ]
        self._last_stream_sources = web_sources

        # Generate an answer grounded in the web results via Bedrock.
        prompt = self._bedrock.format_rag_prompt(question, web_sources)
        answer = self._bedrock.generate(
            prompt=prompt,
            temperature=temperature if temperature is not None else 0.3,
            max_tokens=max_tokens,
        )
        yield answer


def _install_serverless_health(api_server, shim: "ServerlessAgentShim", settings) -> None:
    """Replace the app's /health route with a serverless-aware version.

    Removes the existing GET /health route (which probes a Milvus vector_db)
    and registers one that reports the local OpenSearch + Redis backends. This
    keeps the GUI's status indicator accurate for serverless-local use without
    editing api_server.py.
    """
    app = api_server.app

    # Drop the existing GET /health route(s).
    app.router.routes = [
        r
        for r in app.router.routes
        if not (getattr(r, "path", None) == "/health" and "GET" in getattr(r, "methods", set()))
    ]

    @app.get("/health", tags=["health"])
    def health_serverless():  # noqa: ANN202 - FastAPI route
        opensearch_ok = shim.opensearch_healthy()
        redis_ok = shim.redis_healthy()
        # The knowledge base (vector search) is served by OpenSearch here, so
        # "vector_db_available" tracks OpenSearch, keeping the GUI's existing
        # status field meaningful without changing the frontend contract.
        return {
            "status": "ok" if opensearch_ok else "warning",
            "model": "rag-agent",
            "deployment_mode": "serverless",
            "vector_db": settings.opensearch_endpoint or "opensearch (local)",
            "vector_db_available": opensearch_ok,
            "redis_available": redis_ok,
            "bedrock_model": settings.bedrock_model_override or settings.bedrock_inference_model_id,
            "warning": (
                None
                if opensearch_ok
                else (
                    "OpenSearch is unavailable. Knowledge-base search is "
                    "unavailable. Ensure the local OpenSearch container is running."
                )
            ),
            "web_search_enabled": bool(shim.web_search is not None),
        }


def main() -> int:
    import uvicorn

    import api_server
    from src.config.settings import get_settings

    settings = get_settings()
    if settings.deployment_mode != "serverless":
        logger.error(
            "DEPLOYMENT_MODE is %r, expected 'serverless'. Did .env.serverless-local load?",
            settings.deployment_mode,
        )
        return 2

    logger.info("Building serverless agent shim (Bedrock=%s)...", settings.bedrock_model_override)
    shim = ServerlessAgentShim(settings)

    # Replace the module globals the FastAPI app/handlers read, and neutralise
    # the Local-Mode lifespan so it does not try to build Ollama/Milvus.
    api_server.strands_agent = shim
    api_server.settings = settings
    api_server.initialization_error = None

    # The /api/cache/questions and /v1/cache/questions endpoints serve the
    # module-level `common_questions` list, which the Local-Mode lifespan loads
    # from config/common_questions.json. Our no-op lifespan skips that, so load
    # it here. This is a static config file — no AWS / Milvus dependency.
    try:
        api_server.common_questions = api_server.load_common_questions()
        logger.info("Loaded %d common question(s)", len(api_server.common_questions))
    except Exception as exc:  # noqa: BLE001 - non-fatal; endpoints just return empty
        logger.warning("Could not load common questions: %s", exc)

    # Override /health with a serverless-aware version. The default route in
    # api_server probes a Milvus `vector_db` attribute this shim does not have,
    # so it always reports "vector database unavailable" even though OpenSearch
    # retrieval is working. This replacement reports the real serverless
    # backends (OpenSearch + Redis). LOCAL-ONLY: it lives in this wrapper and
    # never touches api_server.py / src.
    _install_serverless_health(api_server, shim, settings)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _noop_lifespan(_app):
        logger.info("Serverless GUI server ready at http://localhost:%s", settings.api_port)
        yield

    api_server.app.router.lifespan_context = _noop_lifespan

    uvicorn.run(api_server.app, host="0.0.0.0", port=settings.api_port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
