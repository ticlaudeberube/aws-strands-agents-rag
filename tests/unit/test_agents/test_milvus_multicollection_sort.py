"""Unit test for the local multi-collection retrieval global re-rank.

The Milvus retrieval tool searches each collection independently and
concatenates the hits. Before truncating to top_k it must re-sort by
``distance`` (cosine similarity, higher = better) so a strong hit from a later
collection is not dropped in favour of a weaker hit from an earlier one.

Uses injected fakes (no Ollama / Milvus required).
"""

from __future__ import annotations

from src.agents.strands_graph_agent import create_milvus_retrieval_tool
from src.config.settings import Settings


class _FakeOllama:
    def embed_text(self, _text: str, model: str | None = None) -> list[float]:
        return [0.0] * 8


class _TwoCollectionVectorDB:
    """Returns a WEAK hit for the first collection and a STRONG hit for the
    second, so a correct global sort must surface the second collection's hit."""

    def search(
        self, collection_name: str, query_embedding: list[float], limit: int = 5
    ) -> list[dict]:
        if collection_name == "weak":
            return [{"id": 1, "text": "weak hit", "metadata": {}, "distance": 0.20}]
        return [{"id": 2, "text": "strong hit", "metadata": {}, "distance": 0.95}]


def test_multicollection_results_are_globally_sorted_by_distance() -> None:
    # Fakes implement the duck-typed search()/embed_text() the tool uses.
    tool = create_milvus_retrieval_tool(
        _TwoCollectionVectorDB(),  # type: ignore[arg-type]
        _FakeOllama(),  # type: ignore[arg-type]
        Settings(),
    )

    # top_k=1 across two collections: the strong hit (0.95) must win even though
    # the weak collection ("weak") is searched first.
    result = tool("any question", collections=["weak", "strong"], top_k=1)

    sources = result["sources"]
    assert len(sources) == 1
    assert sources[0]["distance"] == 0.95
    assert sources[0]["collection"] == "strong"


def test_multicollection_full_set_is_ordered_high_to_low() -> None:
    tool = create_milvus_retrieval_tool(
        _TwoCollectionVectorDB(),  # type: ignore[arg-type]
        _FakeOllama(),  # type: ignore[arg-type]
        Settings(),
    )
    result = tool("any question", collections=["weak", "strong"], top_k=5)
    distances = [s["distance"] for s in result["sources"]]
    assert distances == sorted(distances, reverse=True)
