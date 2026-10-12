"""Shared document chunking (Local Mode loaders + Serverless indexing pipeline).

This module is the *single source of truth* for how documents are split into
chunks for embedding. Both the local document loaders and the serverless
indexing pipeline (``src/indexing/indexing_handler.py``) call
:func:`chunk_text`, so the chunking behaviour is identical across modes
(design §6a/§6b).

Chunk-size guarantee (Requirement 9.2 / design Property 26)
-----------------------------------------------------------
Every chunk returned by :func:`chunk_text` has a token count less than or equal
to ``max_tokens`` (default: ``settings.max_chunk_length`` == 400). A *token* here
is a whitespace-delimited word, matching the unit the design property measures.
The bound holds for arbitrary input text of any length or content: a single
"word" longer than the limit is itself a hard-split so no chunk can ever exceed
the bound.

The function has no AWS/boto3 dependency and imports cleanly in Local Mode.
"""

from __future__ import annotations

import re

__all__ = ["DEFAULT_MAX_CHUNK_TOKENS", "chunk_text", "count_tokens"]

# Default token bound (Requirement 9.2). Kept in sync with
# ``settings.max_chunk_length`` which the callers pass through.
DEFAULT_MAX_CHUNK_TOKENS = 400

# A token is a maximal run of non-whitespace characters.
_TOKEN_RE = re.compile(r"\S+")


def count_tokens(text: str) -> int:
    """Return the number of whitespace-delimited tokens in ``text``.

    This is the canonical token unit used by the chunk-size guarantee. It is the
    same measure the design property checks against the 400-token bound.
    """
    if not text:
        return 0
    return len(_TOKEN_RE.findall(text))


def _hard_split_long_token(token: str, max_chars: int) -> list[str]:
    """Split a single oversized token into ``max_chars``-sized pieces.

    A token with no internal whitespace (e.g. a very long URL or hash) counts as
    one token, so it never violates the *token* bound on its own. We still split
    it on character length so a pathological input cannot produce an unbounded
    single-"word" chunk, keeping chunks reasonably sized for the embedding model.
    """
    return [token[i : i + max_chars] for i in range(0, len(token), max_chars)]


def chunk_text(
    text: str,
    max_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
    *,
    max_token_chars: int = 2000,
) -> list[str]:
    """Split ``text`` into chunks of at most ``max_tokens`` tokens.

    Args:
        text: Arbitrary input document text.
        max_tokens: Maximum tokens (whitespace-delimited words) per chunk. Must
            be a positive integer; defaults to :data:`DEFAULT_MAX_CHUNK_TOKENS`.
        max_token_chars: Safety bound on the character length of any single
            token; longer tokens are hard-split (keyword-only).

    Returns:
        A list of non-empty chunk strings, each with ``count_tokens(chunk)`` <=
        ``max_tokens``. Returns an empty list for empty/whitespace-only input.

    Raises:
        ValueError: If ``max_tokens`` is not a positive integer.
    """
    if max_tokens <= 0:
        raise ValueError(f"max_tokens must be a positive integer, got {max_tokens}")

    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return []

    # Hard-split any single oversized token so the character growth of a chunk
    # stays bounded; each produced piece is still a single token.
    normalised: list[str] = []
    for token in tokens:
        if len(token) > max_token_chars:
            normalised.extend(_hard_split_long_token(token, max_token_chars))
        else:
            normalised.append(token)

    chunks: list[str] = []
    for start in range(0, len(normalised), max_tokens):
        window = normalised[start : start + max_tokens]
        chunk = " ".join(window)
        if chunk.strip():
            chunks.append(chunk)

    return chunks
