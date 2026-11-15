"""Unit tests for conversation history helpers (src/agents/history.py)."""

from typing import Any

from src.agents.history import last_user_turn, prepare_history, retrieval_text


class TestPrepareHistory:
    def test_empty_or_none_returns_empty(self) -> None:
        assert prepare_history(None) == []
        assert prepare_history([]) == []

    def test_drops_trailing_current_user_message(self) -> None:
        messages = [
            {"role": "user", "content": "What is a vector database?"},
            {"role": "assistant", "content": "A database for embeddings."},
            {"role": "user", "content": "What can I do with it?"},
        ]

        assert prepare_history(messages) == [
            {"role": "user", "content": "What is a vector database?"},
            {"role": "assistant", "content": "A database for embeddings."},
        ]

    def test_keeps_trailing_assistant_message(self) -> None:
        messages = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]

        assert prepare_history(messages) == [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]

    def test_flattens_strands_content_blocks(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"text": "What is RAG?"}]},
            {"role": "assistant", "content": [{"text": "Retrieval augmented generation."}]},
            {"role": "user", "content": "And its cost?"},
        ]

        prepared = prepare_history(messages)

        assert prepared[0] == {"role": "user", "content": "What is RAG?"}
        assert prepared[1] == {
            "role": "assistant",
            "content": "Retrieval augmented generation.",
        }

    def test_skips_unknown_roles_and_blank_content(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "   "},
            {"role": "assistant", "content": [{"toolUse": {}}]},
            {"role": "user", "content": "Real question"},
        ]

        assert prepare_history(messages) == []


class TestLastUserTurn:
    def test_reads_question_rows(self) -> None:
        history = [{"question": "What is a vector database?", "answer": "A store."}]

        assert last_user_turn(history) == "What is a vector database?"

    def test_reads_user_messages(self) -> None:
        history = [{"role": "user", "content": "First"}, {"role": "assistant", "content": "A"}]

        assert last_user_turn(history) == "First"

    def test_returns_none_for_blank_prior_question(self) -> None:
        history = [{"question": "   ", "answer": "A"}]

        assert last_user_turn(history) is None


class TestRetrievalText:
    def test_single_turn_returns_question(self) -> None:
        assert retrieval_text("What is a vector database?", []) == "What is a vector database?"
        assert retrieval_text("What is a vector database?", None) == ("What is a vector database?")

    def test_follow_up_joins_prior_question(self) -> None:
        history = [{"role": "user", "content": "What is a vector database?"}]

        assert retrieval_text("What can I do with it?", history) == (
            "What is a vector database? What can I do with it?"
        )

    def test_uses_most_recent_user_turn(self) -> None:
        history = [
            {"role": "user", "content": "What is a vector database?"},
            {"role": "assistant", "content": "A store for embeddings."},
            {"role": "user", "content": "What is RAG?"},
            {"role": "assistant", "content": "Retrieval augmented generation."},
        ]

        assert retrieval_text("And its cost?", history) == "What is RAG? And its cost?"

    def test_repeated_question_is_not_joined(self) -> None:
        history = [{"role": "user", "content": "What is RAG?"}]

        assert retrieval_text("What is RAG?", history) == "What is RAG?"

    def test_history_without_user_turn_returns_question(self) -> None:
        history = [{"role": "assistant", "content": "Hello"}]

        assert retrieval_text("What is RAG?", history) == "What is RAG?"
