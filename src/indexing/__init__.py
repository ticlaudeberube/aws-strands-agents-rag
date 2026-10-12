"""Document indexing pipeline (shared chunking + serverless S3 handler).

This package holds logic shared between Local Mode document loading and the
Serverless Mode S3-triggered indexing Lambda:

- :mod:`src.indexing.chunking` — the single shared chunking function that bounds
  every chunk to ``settings.max_chunk_length`` tokens (Requirement 9.2).
- :mod:`src.indexing.indexing_handler` — the serverless ``lambda_handler`` that
  processes S3 ``ObjectCreated`` events (Requirements 9.1, 9.3, 9.4, 9.5).

Both modules import cleanly without ``boto3`` / AWS SDK dependencies installed;
AWS clients are constructed lazily, so importing this package never affects
Local Mode.
"""

from src.indexing.chunking import DEFAULT_MAX_CHUNK_TOKENS, chunk_text, count_tokens

__all__ = ["DEFAULT_MAX_CHUNK_TOKENS", "chunk_text", "count_tokens"]
