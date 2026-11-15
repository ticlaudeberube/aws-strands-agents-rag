"""Pre-routing guardrails shared by local and serverless answer paths.

``shared_route`` (``strands_graph_agent``) runs the security check before
routing. The scope check runs inside ``route_rag_query`` after the query is
embedded, so it reuses the same vector for the cache. Both checks fail closed:
an exception blocks the query instead of letting it through.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from src.agents.history import last_user_turn
from src.agents.topic_scope import OUT_OF_SCOPE_ANSWER, is_question_in_scope

logger = logging.getLogger(__name__)

__all__ = [
    "ANCHORS",
    "OUT_OF_SCOPE_ANSWER",
    "SECURITY_REFUSAL_ANSWER",
    "GuardBlock",
    "ScopeGate",
    "is_security_attack",
    "keyword_in_scope",
    "screen_security",
]

SECURITY_REFUSAL_ANSWER = (
    "I detected a security concern with your query. Please rephrase and ask a legitimate question."
)

# Phrases matched as substrings against the lowercased query, with a
# normalized copy that expands common contractions.
JAILBREAK_PATTERNS: tuple[str, ...] = (
    "forget your instruction",
    "forget you are a",
    "forget you",
    "forget about",
    "ignore your instruction",
    "ignore your system",
    "disregard your instruction",
    "override your",
    "bypass your",
    "bypass the",
    "bypass security",
    "bypass restrictions",
    "ignore the system prompt",
    "ignore the previous instruction",
    "you are no longer",
    "ignore the scope",
    "ignore the limitation",
    "disregard",
    "jailbreak",
    "hack",
    "offshore account",
    "launder",
    "ignore the rule",
    "pretend you are",
    "role play as",
    "act as if you",
    "what is your hidden",
    "what is your system prompt",
    "reveal your prompt",
    "show me your instruction",
    "dump your system prompt",
    "tell me your secret",
    "do not follow your",
    "don't follow your",
)

# Command phrases matched on word boundaries, so "steal" does not match
# "stealth". Bare verbs that appear in ordinary questions (for example
# "delete an index") are replaced by phrases that name a destructive target.
COMMAND_PHRASES: tuple[str, ...] = (
    "send money",
    "transfer money",
    "steal",
    "drop table",
    "sql injection",
    "fork bomb",
    "ddos",
    "malware",
    "delete all",
    "delete user",
    "delete records",
    "delete the database",
)

_COMMAND_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(phrase) for phrase in COMMAND_PHRASES) + r")\b"
)

# Code-injection tokens. Matched as substrings on the lowercased query.
INJECTION_PATTERNS: tuple[str, ...] = (
    "'; drop",
    "'; delete",
    "'; update",
    "'; insert",
    "rm -rf",
    "exec(",
    "eval(",
    "__import__",
    "subprocess",
    "os.system",
    "shell=true",
)


def _detect_attack(question: str) -> bool:
    """Return True when the query matches a jailbreak, command, or injection pattern."""
    question_lower = question.lower()
    question_normalized = (
        question_lower.replace("you're", "you are")
        .replace("don't", "do not")
        .replace("what's", "what is")
    )

    for pattern in JAILBREAK_PATTERNS:
        if pattern in question_lower or pattern in question_normalized:
            logger.warning("[SECURITY_ATTACK] Jailbreak detected: '%s'", pattern)
            return True

    match = _COMMAND_RE.search(question_lower)
    if match:
        logger.warning("[SECURITY_ATTACK] Command injection detected: '%s'", match.group(0))
        return True

    for pattern in INJECTION_PATTERNS:
        if pattern in question_lower:
            logger.warning("[SECURITY_ATTACK] Injection detected: '%s'", pattern)
            return True

    return False


def is_security_attack(question: str) -> bool:
    """Return True when the query should be blocked as a security risk.

    Fails closed: if the detector raises, the query is treated as an attack.
    """
    try:
        return _detect_attack(question)
    except Exception:
        logger.exception("[SECURITY_CHECK] Detector failed; blocking query (fail closed)")
        return True


# In-scope anchor descriptions. The scope gate scores each query against these.
# Changing them changes the calibrated thresholds, so re-run
# scripts/eval_scope.py before editing.
ANCHORS: tuple[str, ...] = (
    "What is a vector database and how does it store embeddings?",
    "How does approximate nearest neighbor search work?",
    "How do I build a retrieval augmented generation (RAG) pipeline?",
    "Which embedding model should I use for semantic search?",
    "How do HNSW and IVF vector indexes trade recall for speed?",
    "How do I configure OpenSearch or Milvus for vector search?",
    "How do I chunk documents for retrieval?",
    "How do I evaluate retrieval quality and answer grounding?",
)


def keyword_in_scope(question: str) -> bool:
    """Keyword scope check. Kept as the offline baseline for ``scripts/eval_scope.py``.

    The runtime scope decision uses :class:`ScopeGate`.
    """
    try:
        return is_question_in_scope(question)
    except Exception:
        logger.exception("[SCOPE_CHECK] Keyword classifier failed; rejecting query (fail closed)")
        return False


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Embedding dimensions differ: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


_last_user_turn = last_user_turn


class ScopeGate:
    """Embedding-based scope check against :data:`ANCHORS`.

    A query is in scope when its highest cosine similarity to any anchor is at
    least ``threshold``. Anchor vectors are embedded on first use and cached for
    the life of the gate. ``embed`` must be the same model and output shape used
    to calibrate the threshold: the local client (nomic) or the serverless client
    (Titan, PCA 768).

    Fails closed: an embedding error, a dimension mismatch, or an empty vector
    rejects the query.
    """

    def __init__(self, embed: Callable[[str], list[float]], threshold: float) -> None:
        self._embed = embed
        self._threshold = threshold
        self._anchor_vectors: list[list[float]] | None = None

    @property
    def threshold(self) -> float:
        return self._threshold

    def _anchors(self) -> list[list[float]]:
        if self._anchor_vectors is None:
            self._anchor_vectors = [self._embed(anchor) for anchor in ANCHORS]
        return self._anchor_vectors

    def allows(
        self,
        question: str,
        query_vector: list[float] | None = None,
        history: list[dict] | None = None,
    ) -> bool:
        """Return True when the query is in scope.

        Args:
            question: The query text.
            query_vector: An embedding of ``question`` from the same client. Reused
                when there is no prior turn, so no second embedding call is made.
            history: Prior turns. When the last user turn exists, the gate embeds
                that turn plus ``question``. The thresholds were calibrated on this
                form, and follow-ups such as "what about its cost?" need it.
        """
        try:
            prior = _last_user_turn(history)
            if prior is not None:
                vector = self._embed(f"{prior} {question}")
            elif query_vector is not None:
                vector = query_vector
            else:
                vector = self._embed(question)
            best = max(_cosine(vector, anchor) for anchor in self._anchors())
        except Exception:
            logger.exception("[SCOPE_CHECK] Embedding scope check failed; rejecting query")
            return False
        allowed = best >= self._threshold
        if not allowed:
            logger.info("[SCOPE_CHECK] Out of scope (best anchor similarity %.3f)", best)
        return allowed


@dataclass(frozen=True)
class GuardBlock:
    """A query rejected before routing.

    Attributes:
        tier: ``"security"`` or ``"topic"``; matches the ``tier_used`` field.
        answer: Refusal text returned to the user.
    """

    tier: str
    answer: str


def screen_security(question: str) -> GuardBlock | None:
    """Return a security :class:`GuardBlock` for an attack, otherwise ``None``."""
    if is_security_attack(question):
        return GuardBlock(tier="security", answer=SECURITY_REFUSAL_ANSWER)
    return None
