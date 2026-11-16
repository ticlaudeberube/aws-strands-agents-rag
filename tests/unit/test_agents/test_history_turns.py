"""Unit tests for message normalization and the joined recent-question text (src/agents/history.py)."""

from typing import Any

from src.agents.history import (
    normalize_turns,
    recent_user_questions,
    retrieval_text,
)

THREE_HOP = [
    {"role": "user", "content": "What is Milvus?"},
    {"role": "assistant", "content": "A vector database."},
    {"role": "user", "content": "What can I do with it?"},
    {"role": "assistant", "content": "Store and search embeddings."},
    {"role": "user", "content": "Can it do hybrid search?"},
    {"role": "assistant", "content": "Yes, with BM25 plus vectors."},
]


class TestNormalizeTurns:
    def test_dynamodb_rows_yield_user_then_assistant(self) -> None:
        rows = [{"question": "What is RAG?", "answer": "Retrieval augmented generation."}]
        assert normalize_turns(rows) == [
            ("user", "What is RAG?"),
            ("assistant", "Retrieval augmented generation."),
        ]

    def test_message_content_blocks_are_flattened(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"text": "What is HNSW?"}]},
            {"role": "system", "content": "ignored"},
        ]
        assert normalize_turns(messages) == [("user", "What is HNSW?")]


class TestRecentUserQuestions:
    def test_returns_last_n_oldest_first(self) -> None:
        assert recent_user_questions(THREE_HOP, 2) == [
            "What can I do with it?",
            "Can it do hybrid search?",
        ]

    def test_zero_limit_returns_nothing(self) -> None:
        assert recent_user_questions(THREE_HOP, 0) == []


class TestRetrievalTextTurns:
    def test_default_joins_one_prior_question(self) -> None:
        # Prior turns only: the final user question is not part of the history.
        history = THREE_HOP[:-2]
        assert retrieval_text("Can it do hybrid search?", history) == (
            "What can I do with it? Can it do hybrid search?"
        )

    def test_three_turns_join_all_recent_questions(self) -> None:
        assert retrieval_text("Can it do hybrid search?", THREE_HOP, turns=3) == (
            "What is Milvus? What can I do with it? Can it do hybrid search?"
        )
