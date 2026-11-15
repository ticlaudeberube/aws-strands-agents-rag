"""Unit tests for the follow-up retrieval eval scoring (scripts/eval_followup.py).

The embedding and KB search are replaced with fakes; no Ollama or OpenSearch
is contacted.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_EVAL_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "eval_followup.py"
_spec = importlib.util.spec_from_file_location("eval_followup", _EVAL_PATH)
assert _spec and _spec.loader
eval_followup = importlib.util.module_from_spec(_spec)
sys.modules["eval_followup"] = eval_followup
_spec.loader.exec_module(eval_followup)

PAIRS_PATH = Path(__file__).resolve().parent.parent.parent / "eval" / "followup_pairs.jsonl"


def _pair(category: str, expected: list[str]) -> Any:
    return eval_followup.Pair(
        id=f"{category}-1",
        category=category,
        history=[{"role": "user", "content": "What is Milvus?"}],
        question="What can I do with it?",
        expected_terms=expected,
    )


def test_is_hit_matches_any_term_case_insensitively() -> None:
    chunks = ["Milvus is a vector database.", "Unrelated text."]

    assert eval_followup.is_hit(chunks, ["milvus"]) is True
    assert eval_followup.is_hit(chunks, ["HNSW", "Pinecone"]) is False


def test_is_hit_is_false_without_chunks() -> None:
    assert eval_followup.is_hit([], ["Milvus"]) is False


def test_retrieval_query_joins_only_when_requested() -> None:
    pair = _pair(eval_followup.FOLLOW_UP, ["Milvus"])

    assert eval_followup.retrieval_query(pair, joined=False) == "What can I do with it?"
    assert eval_followup.retrieval_query(pair, joined=True) == (
        "What is Milvus? What can I do with it?"
    )


def test_evaluate_records_raw_and_joined_hits() -> None:
    pair = _pair(eval_followup.FOLLOW_UP, ["Milvus"])

    def fake_search(text: str, top_k: int, index: str) -> list[str]:
        assert top_k == 3
        assert index == "rag-kb"
        return ["Milvus is a vector database."] if "What is Milvus?" in text else ["Other"]

    rows = eval_followup.evaluate([pair], fake_search, top_k=3, index="rag-kb")

    assert rows[0]["raw_hit"] is False
    assert rows[0]["joined_hit"] is True


def test_summarize_reports_rates_per_category() -> None:
    rows = [
        {"category": "follow_up", "raw_hit": False, "joined_hit": True},
        {"category": "follow_up", "raw_hit": True, "joined_hit": True},
        {"category": "topic_switch", "raw_hit": True, "joined_hit": False},
    ]

    summary = eval_followup.summarize(rows)

    assert summary["follow_up"]["raw_hit_rate"] == 0.5
    assert summary["follow_up"]["joined_hit_rate"] == 1.0
    assert summary["topic_switch"]["joined_hit_rate"] == 0.0


def test_decide_keeps_join_only_when_it_helps_and_switches_hold() -> None:
    helps = {
        "follow_up": {"cases": 2.0, "raw_hit_rate": 0.5, "joined_hit_rate": 1.0},
        "topic_switch": {"cases": 2.0, "raw_hit_rate": 1.0, "joined_hit_rate": 1.0},
    }
    hurts_switches = {
        "follow_up": {"cases": 2.0, "raw_hit_rate": 0.5, "joined_hit_rate": 1.0},
        "topic_switch": {"cases": 2.0, "raw_hit_rate": 1.0, "joined_hit_rate": 0.5},
    }

    assert eval_followup.decide(helps).startswith("keep join")
    assert eval_followup.decide(hurts_switches).startswith("revise join")
    assert eval_followup.decide({}).startswith("insufficient data")


def test_shipped_pairs_cover_both_categories_with_expected_terms() -> None:
    pairs = eval_followup.load_pairs(PAIRS_PATH)

    categories = {pair.category for pair in pairs}
    assert categories == {eval_followup.FOLLOW_UP, eval_followup.TOPIC_SWITCH}
    assert all(pair.expected_terms for pair in pairs)
    assert all(pair.history for pair in pairs)
