"""Routing tests for the follow-up condenser in ``route_rag_query``.

The condenser rewrites a follow-up into one standalone question. That text must
drive the scope gate, the embedding, and the KB search. A failing condenser falls
back to joining the last few user questions.
"""

from __future__ import annotations

from typing import Any

from src.agents.rag_routing import route_rag_query

HISTORY = [
    {"role": "user", "content": "What is Milvus?"},
    {"role": "assistant", "content": "A vector database."},
    {"role": "user", "content": "What can I do with it?"},
    {"role": "assistant", "content": "Store and search embeddings."},
]
QUESTION = "Can it do hybrid search?"
REWRITE = "Does Milvus support hybrid search?"
STRONG_KB_HIT = [
    {"id": "1", "text": "Milvus supports hybrid search.", "metadata": {}, "distance": 0.9}
]


class _LLM:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [0.1] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        return "Milvus supports hybrid search."


class _VectorStore:
    def __init__(self) -> None:
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
        return list(STRONG_KB_HIT)


class _ScopeGate:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    def __call__(self, question: str, query_vector: Any, history: Any) -> bool:
        self.calls.append((question, query_vector, history))
        return True


class _Condenser:
    def __init__(self, reply: str = REWRITE, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply


class _SemanticCache:
    def __init__(self) -> None:
        self.searches = 0
        self.stores = 0

    def search_semantic_cache(self, question: str, query_vector: Any, threshold: float) -> None:
        self.searches += 1
        return None

    def store_semantic_cache(self, **_kwargs: Any) -> None:
        self.stores += 1


def _route(
    *,
    history: list[dict] | None,
    llm: _LLM,
    vector_store: _VectorStore,
    scope: _ScopeGate | None = None,
    condenser: Any = None,
    semantic_cache: Any = None,
) -> Any:
    return route_rag_query(
        QUESTION,
        llm=llm,
        vector_store=vector_store,
        cache=None,
        semantic_cache=semantic_cache,
        kb_index="rag-kb",
        history=history,
        scope_gate=scope,
        condenser=condenser,
    )


def test_rewrite_drives_embedding_and_kb_search() -> None:
    llm = _LLM()
    vector_store = _VectorStore()

    _route(history=HISTORY, llm=llm, vector_store=vector_store, condenser=_Condenser())

    assert llm.embedded[0] == REWRITE
    assert vector_store.query_texts and all(text == REWRITE for text in vector_store.query_texts)


def test_scope_gate_judges_the_rewrite_with_its_vector() -> None:
    scope = _ScopeGate()
    llm = _LLM()

    _route(
        history=HISTORY,
        llm=llm,
        vector_store=_VectorStore(),
        scope=scope,
        condenser=_Condenser(),
    )

    question, vector, history = scope.calls[0]
    assert question == REWRITE
    assert vector == [0.1] * 8
    assert history is None


def test_condenser_prompt_contains_prior_turns() -> None:
    condenser = _Condenser()

    _route(history=HISTORY, llm=_LLM(), vector_store=_VectorStore(), condenser=condenser)

    assert len(condenser.prompts) == 1
    assert "User: What is Milvus?" in condenser.prompts[0]
    assert f"Final user message: {QUESTION}" in condenser.prompts[0]


def test_first_turn_does_not_call_condenser() -> None:
    condenser = _Condenser()
    llm = _LLM()

    _route(history=None, llm=llm, vector_store=_VectorStore(), condenser=condenser)

    assert condenser.prompts == []
    assert llm.embedded[0] == QUESTION


def test_condenser_failure_falls_back_to_recent_questions() -> None:
    llm = _LLM()

    _route(
        history=HISTORY,
        llm=llm,
        vector_store=_VectorStore(),
        condenser=_Condenser(error=RuntimeError("model unavailable")),
    )

    assert llm.embedded[0] == "What is Milvus? What can I do with it? Can it do hybrid search?"


def test_without_condenser_joins_recent_user_questions() -> None:
    llm = _LLM()

    _route(history=HISTORY, llm=llm, vector_store=_VectorStore(), condenser=None)

    assert llm.embedded[0] == "What is Milvus? What can I do with it? Can it do hybrid search?"


def test_condensed_follow_up_still_skips_semantic_cache() -> None:
    semantic_cache = _SemanticCache()

    _route(
        history=HISTORY,
        llm=_LLM(),
        vector_store=_VectorStore(),
        condenser=_Condenser(),
        semantic_cache=semantic_cache,
    )

    assert semantic_cache.searches == 0
    assert semantic_cache.stores == 0
