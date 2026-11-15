"""Conversation history helpers shared by the scope gate and the routing pipeline.

Two history shapes reach the shared route:

- ``{"question": ..., "answer": ...}`` rows from the serverless DynamoDB session.
- ``{"role": ..., "content": ...}`` messages from the local API and the CLI.

A *follow-up* is any request that carries prior turns. For a follow-up, the
router rewrites the conversation into one standalone question (see
:func:`condense_question`). The rewrite feeds the scope gate, embedding, and KB
search. If the rewrite fails, the router falls back to joining the most recent
user questions with the current one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CONDENSE_MAX_CHARS",
    "FALLBACK_USER_TURNS",
    "build_condense_prompt",
    "clean_condensed",
    "condense_question",
    "last_user_turn",
    "normalize_turns",
    "prepare_history",
    "recent_user_questions",
    "retrieval_text",
]

_USER_ROLE = "user"
_ASSISTANT_ROLE = "assistant"
_VALID_ROLES = frozenset({_USER_ROLE, _ASSISTANT_ROLE})

# Longest standalone question accepted from the condenser. Longer output is
# treated as a failed rewrite.
CONDENSE_MAX_CHARS = 300
# Most recent turns included in the condenser transcript.
CONDENSE_TRANSCRIPT_TURNS = 6
# User questions joined when the condenser fails.
FALLBACK_USER_TURNS = 3
_STANDALONE_PREFIX = "standalone question:"

_CONDENSE_PROMPT = """Rewrite the final user message as one standalone question that makes sense without the conversation.
- Replace pronouns and references (it, its, that, they, this) with the specific subject named earlier.
- Use the subject from the most recent discussion of that subject. Keep every word that names a subject or feature.
- If the final message starts a new topic, keep only the new topic. Do not carry over the earlier topic.
- Reply with only the question.

Example 1
Conversation:
User: What is Redis?
Assistant: An in-memory data store.
User: Does it persist data?
Assistant: Yes, it can snapshot to disk.
Final user message: Is it good for caching my app?
Standalone question: Is Redis good for caching my app?

Example 2
Conversation:
User: What is Redis?
Assistant: An in-memory data store.
Final user message: How do I tune a Postgres index?
Standalone question: How do I tune a Postgres index?

Conversation:
{transcript}
Final user message: {question}
Standalone question:"""


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


def build_condense_prompt(question: str, history: list[dict[str, Any]] | None) -> str:
    """Return the rewrite prompt: the recent transcript plus the current question."""
    lines = []
    for role, text in normalize_turns(history)[-CONDENSE_TRANSCRIPT_TURNS:]:
        label = "User" if role == _USER_ROLE else "Assistant"
        lines.append(f"{label}: {text}")
    return _CONDENSE_PROMPT.format(transcript="\n".join(lines), question=question)


def clean_condensed(raw: str) -> str | None:
    """Return the first non-empty line of a rewrite, or ``None`` when unusable.

    Strips surrounding quotes and a leading "Standalone question:" label. Output
    longer than :data:`CONDENSE_MAX_CHARS` is rejected.
    """
    for line in str(raw).splitlines():
        candidate = line.strip().strip('"').strip()
        if candidate.lower().startswith(_STANDALONE_PREFIX):
            candidate = candidate[len(_STANDALONE_PREFIX) :].strip().strip('"').strip()
        if not candidate:
            continue
        return candidate if len(candidate) <= CONDENSE_MAX_CHARS else None
    return None


def condense_question(
    question: str,
    history: list[dict[str, Any]] | None,
    generate: Callable[[str], str],
    fallback_turns: int = FALLBACK_USER_TURNS,
) -> str:
    """Return one standalone question for a follow-up, using the LLM ``generate``.

    Falls back to :func:`retrieval_text` over the last ``fallback_turns`` user
    questions when the call raises, returns no usable text, or returns the current
    question unchanged (no rewrite happened).
    """
    if not history:
        return question
    fallback = retrieval_text(question, history, turns=fallback_turns)
    try:
        raw = generate(build_condense_prompt(question, history))
    except Exception as exc:  # noqa: BLE001 - any failure degrades to the join
        logger.warning(
            "[CONDENSE] Rewrite call failed (%s); using fallback join", type(exc).__name__
        )
        return fallback

    candidate = clean_condensed(raw)
    if candidate is None:
        logger.warning("[CONDENSE] Rewrite was empty or too long; using fallback join")
        return fallback
    if candidate.lower() == question.strip().lower():
        logger.info("[CONDENSE] Rewrite matched the question; using fallback join")
        return fallback
    logger.info("[CONDENSE] Rewrote follow-up into a standalone question")
    return candidate
