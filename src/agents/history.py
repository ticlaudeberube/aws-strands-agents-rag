"""Conversation history helpers shared by the scope gate and the routing pipeline.

Two history shapes reach the shared route:
- ``{"question": ..., "answer": ...}`` rows from the serverless DynamoDB session.
- ``{"role": ..., "content": ...}`` messages from the local API and the CLI.

A *follow-up* is any request that carries prior turns. For a follow-up, the router
joins the most recent user questions with the current one to form the search text
(see :func:`retrieval_text`). The join is deterministic and needs no model call.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "FALLBACK_USER_TURNS",
    "last_user_turn",
    "normalize_turns",
    "prepare_history",
    "recent_user_questions",
    "retrieval_text",
]

_USER_ROLE = "user"
_ASSISTANT_ROLE = "assistant"
_VALID_ROLES = frozenset({_USER_ROLE, _ASSISTANT_ROLE})

# Default number of recent user questions joined into the search text.
FALLBACK_USER_TURNS = 3


def last_user_turn(history: list[dict[str, Any]] | None) -> str | None:
    """Return the most recent non-blank user question from ``history``, or ``None``.

    Accepts both ``{"question": ..., "answer": ...}`` rows (serverless DynamoDB)
    and ``{"role": ..., "content": ...}`` messages.
    """
    for turn in reversed(history or []):
        question = turn.get("question")
        if isinstance(question, str) and question.strip():
            return question
        content = turn.get("content")
        if turn.get("role") == _USER_ROLE and isinstance(content, str) and content.strip():
            return content
    return None


def _message_text(content: Any) -> str:
    """Flatten message content to text.

    Accepts a plain string or a list of Strands-style content blocks such as
    ``[{"text": "..."}]``. Blocks without text are ignored.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        return " ".join(part.strip() for part in parts if part.strip())
    return ""


def normalize_turns(history: list[dict[str, Any]] | None) -> list[tuple[str, str]]:
    """Return ``(role, text)`` pairs in conversation order, for either history shape.

    A DynamoDB row yields its question as a user turn and its answer as an
    assistant turn. Blank text and unknown roles are skipped.
    """
    turns: list[tuple[str, str]] = []
    for turn in history or []:
        question = turn.get("question")
        if isinstance(question, str):
            if question.strip():
                turns.append((_USER_ROLE, question.strip()))
            answer = turn.get("answer")
            if isinstance(answer, str) and answer.strip():
                turns.append((_ASSISTANT_ROLE, answer.strip()))
            continue
        role = turn.get("role")
        text = _message_text(turn.get("content"))
        if role in _VALID_ROLES and text:
            turns.append((str(role), text))
    return turns


def recent_user_questions(history: list[dict[str, Any]] | None, limit: int) -> list[str]:
    """Return up to ``limit`` of the most recent user questions, oldest first."""
    if limit <= 0:
        return []
    questions = [text for role, text in normalize_turns(history) if role == _USER_ROLE]
    return questions[-limit:]


def prepare_history(messages: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Return prior turns as ``{"role", "content"}`` dicts with plain-text content.

    The final entry is dropped when it is a user message, because that message is
    the current question. Entries with an unknown role or no text are skipped.
    """
    if not messages:
        return []
    turns = list(messages)
    if turns and turns[-1].get("role") == _USER_ROLE:
        turns = turns[:-1]

    prepared: list[dict[str, str]] = []
    for turn in turns:
        role = turn.get("role")
        if role not in _VALID_ROLES:
            continue
        text = _message_text(turn.get("content"))
        if text:
            prepared.append({"role": str(role), "content": text})
    return prepared


def retrieval_text(
    question: str,
    history: list[dict[str, Any]] | None,
    turns: int = 1,
) -> str:
    """Return the text to embed and search for ``question`` without an LLM rewrite.

    Joins up to ``turns`` recent user questions (oldest first) with the current
    question. Prior questions that repeat the current question are skipped. With
    no usable prior turn, returns the question unchanged.
    """
    current = question.strip()
    prior = [q for q in recent_user_questions(history, turns) if q.strip() != current]
    if not prior:
        return question
    return " ".join([*(q.strip() for q in prior), question])
