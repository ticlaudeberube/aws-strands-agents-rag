"""Unit tests for multi-turn retrieval text and the follow-up condenser (src/agents/history.py)."""

from typing import Any

from src.agents.history import (
    CONDENSE_MAX_CHARS,
    FALLBACK_USER_TURNS,
    build_condense_prompt,
    clean_condensed,
    condense_question,
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


class _Generator:
    """Records prompts and returns a fixed reply, or raises when configured to."""

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply


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


class TestBuildCondensePrompt:
    def test_prompt_contains_transcript_and_question(self) -> None:
        prompt = build_condense_prompt("Can it do hybrid search?", THREE_HOP)

        assert "User: What is Milvus?" in prompt
        assert "Assistant: A vector database." in prompt
        assert "Final user message: Can it do hybrid search?" in prompt
        assert prompt.endswith("Standalone question:")


class TestCleanCondensed:
    def test_strips_label_and_quotes(self) -> None:
        raw = '  Standalone question: "Does Milvus support hybrid search?"  '

        assert clean_condensed(raw) == "Does Milvus support hybrid search?"

    def test_uses_first_non_empty_line(self) -> None:
        assert clean_condensed("\n\nDoes Milvus scale?\nExtra commentary") == "Does Milvus scale?"

    def test_empty_output_is_rejected(self) -> None:
        assert clean_condensed("   \n  ") is None

    def test_overlong_output_is_rejected(self) -> None:
        assert clean_condensed("x" * (CONDENSE_MAX_CHARS + 1)) is None


class TestCondenseQuestion:
    def test_no_history_returns_question_without_calling_model(self) -> None:
        generator = _Generator(reply="unused")

        assert condense_question("What is Milvus?", None, generator) == "What is Milvus?"
        assert generator.prompts == []

    def test_uses_model_rewrite(self) -> None:
        generator = _Generator(reply="Does Milvus support hybrid search?")

        result = condense_question("Can it do hybrid search?", THREE_HOP, generator)

        assert result == "Does Milvus support hybrid search?"
        assert len(generator.prompts) == 1

    def test_model_error_falls_back_to_recent_questions(self) -> None:
        generator = _Generator(error=RuntimeError("timeout"))

        result = condense_question("Can it do hybrid search?", THREE_HOP, generator)

        assert result == retrieval_text(
            "Can it do hybrid search?", THREE_HOP, turns=FALLBACK_USER_TURNS
        )

    def test_empty_rewrite_falls_back(self) -> None:
        generator = _Generator(reply="")

        result = condense_question("Can it do hybrid search?", THREE_HOP, generator)

        assert "What is Milvus?" in result
        assert result.endswith("Can it do hybrid search?")

    def test_rewrite_equal_to_question_falls_back(self) -> None:
        generator = _Generator(reply="can it do hybrid search?")

        result = condense_question("Can it do hybrid search?", THREE_HOP, generator)

        assert result == retrieval_text(
            "Can it do hybrid search?", THREE_HOP, turns=FALLBACK_USER_TURNS
        )
