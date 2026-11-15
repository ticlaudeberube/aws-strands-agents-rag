"""Unit tests for follow-up handling in ``route_rag_query``.

A follow-up carries prior turns. The router must embed and search the joined
retrieval text, and it must not read or write any cache layer for that request.
Single-turn requests keep their existing cache behaviour.
"""

from __future__ import annotations

from typing import Any

from src.agents.rag_routing import route_rag_query

PRIOR_QUESTION = "What is a vector database?"
FOLLOW_UP = "What can I do with it?"
JOINED_TEXT = f"{PRIOR_QUESTION} {FOLLOW_UP}"
HISTORY = [
    {"role": "user", "content": PRIOR_QUESTION},
    {"role": "assistant", "content": "A database that stores embeddings."},
]
STRONG_KB_HIT = [
    {
        "id": "1",
        "text": "Vector databases index embeddings for similarity search.",
        "metadata": {},
        "distance": 0.9,
    }
]


class _RecordingLLM:
    """LLMClient fake that records embedding inputs and generation prompts."""

    def __init__(self) -> None:
        self.embedded: list[str] = []
        self.prompts: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [0.1] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        self.prompts.append(prompt)
        return "A vector database supports similarity search."


class _RecordingVectorStore:
    """VectorStore fake that records each KB query text."""

    def __init__(self, results: list[dict]) -> None:
        self._results = results
        self.query_texts: list[str | None] = []

    def knn_search(
        self,
        _index: str,
        _vector: list[float],
        _k: int,
        filters: dict | None = None,
        query_text: str | None = None,
    ) -> list[dict]:
        self.query_texts.append(query_text)
        return list(self._results)


class _RecordingCache:
    """CacheBackend fake that records every get and set call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_embedding(self, key: str) -> None:
        self.calls.append(f"get_embedding:{key}")
        return None

    def set_embedding(self, key: str, _vector: list[float]) -> None:
        self.calls.append(f"set_embedding:{key}")

    def get_search_results(self, key: str) -> None:
        self.calls.append(f"get_search_results:{key}")
        return None

    def set_search_results(self, key: str, _results: list[dict]) -> None:
        self.calls.append(f"set_search_results:{key}")


class _RecordingSemanticCache:
    """SemanticCache fake that records lookups and stores."""

    def __init__(self) -> None:
        self.searches = 0
        self.stores = 0

    def search_semantic_cache(
        self,
        question: str,
        query_vector: list[float],
        threshold: float,
    ) -> None:
        self.searches += 1
        return None

    def store_semantic_cache(
        self,
        question: str,
        query_vector: list[float],
        answer: str,
        sources: list[dict],
    ) -> None:
        self.stores += 1


class _RecordingWebSearch:
    """Web search fake that records the queries it receives."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, max_results: int = 3) -> tuple[list[dict], str]:
        self.queries.append(query)
        return (
            [{"title": "Vector DB", "url": "https://example.com", "snippet": "Stores vectors."}],
            "success",
        )


def _route(
    question: str,
    *,
    history: list[dict] | None,
    llm: _RecordingLLM,
    vector_store: _RecordingVectorStore,
    cache: _RecordingCache | None,
    semantic_cache: _RecordingSemanticCache | None,
    web_search: Any = None,
) -> Any:
    return route_rag_query(
        question,
        llm=llm,
        vector_store=vector_store,
        cache=cache,
        semantic_cache=semantic_cache,
        web_search=web_search,
        kb_index="rag-kb",
        history=history,
    )


def test_follow_up_embeds_joined_retrieval_text() -> None:
    llm = _RecordingLLM()

    _route(
        FOLLOW_UP,
        history=HISTORY,
        llm=llm,
        vector_store=_RecordingVectorStore(STRONG_KB_HIT),
        cache=None,
        semantic_cache=None,
    )

    assert llm.embedded[0] == JOINED_TEXT


def test_follow_up_kb_search_uses_joined_text() -> None:
    vector_store = _RecordingVectorStore(STRONG_KB_HIT)

    _route(
        FOLLOW_UP,
        history=HISTORY,
        llm=_RecordingLLM(),
        vector_store=vector_store,
        cache=None,
        semantic_cache=None,
    )

    assert vector_store.query_texts
    assert all(text == JOINED_TEXT for text in vector_store.query_texts)


def test_follow_up_bypasses_every_cache_layer() -> None:
    cache = _RecordingCache()
    semantic_cache = _RecordingSemanticCache()

    result = _route(
        FOLLOW_UP,
        history=HISTORY,
        llm=_RecordingLLM(),
        vector_store=_RecordingVectorStore(STRONG_KB_HIT),
        cache=cache,
        semantic_cache=semantic_cache,
    )

    assert cache.calls == []
    assert semantic_cache.searches == 0
    assert semantic_cache.stores == 0
    assert result.cache_hit is False


def test_follow_up_generation_prompt_includes_prior_turn() -> None:
    llm = _RecordingLLM()

    _route(
        FOLLOW_UP,
        history=HISTORY,
        llm=llm,
        vector_store=_RecordingVectorStore(STRONG_KB_HIT),
        cache=None,
        semantic_cache=None,
    )

    assert llm.prompts
    assert PRIOR_QUESTION in llm.prompts[0]
    assert FOLLOW_UP in llm.prompts[0]


def test_follow_up_web_fallback_uses_joined_text() -> None:
    web_search = _RecordingWebSearch()
    weak_kb = [{"id": "1", "text": "Unrelated", "metadata": {}, "distance": 0.01}]

    _route(
        FOLLOW_UP,
        history=HISTORY,
        llm=_RecordingLLM(),
        vector_store=_RecordingVectorStore(weak_kb),
        cache=None,
        semantic_cache=None,
        web_search=web_search,
    )

    assert web_search.queries == [JOINED_TEXT]


def test_single_turn_still_uses_embedding_cache() -> None:
    cache = _RecordingCache()
    llm = _RecordingLLM()

    _route(
        PRIOR_QUESTION,
        history=None,
        llm=llm,
        vector_store=_RecordingVectorStore(STRONG_KB_HIT),
        cache=cache,
        semantic_cache=None,
    )

    assert llm.embedded[0] == PRIOR_QUESTION
    assert any(call.startswith("get_embedding:") for call in cache.calls)


def test_single_turn_embeds_raw_question_without_join() -> None:
    llm = _RecordingLLM()

    _route(
        PRIOR_QUESTION,
        history=[],
        llm=llm,
        vector_store=_RecordingVectorStore(STRONG_KB_HIT),
        cache=None,
        semantic_cache=None,
    )

    assert llm.embedded[0] == PRIOR_QUESTION
