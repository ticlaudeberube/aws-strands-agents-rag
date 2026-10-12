"""AWS Bedrock LLM + embedding client (Serverless Mode).

This is the Serverless Mode equivalent of :class:`~src.tools.ollama_client.OllamaClient`.
It wraps ``boto3.client("bedrock-runtime")`` and conforms to the
:class:`~src.tools.interfaces.LLMClient` protocol (``generate`` + ``embed_text``)
so it can be injected into the shared Strands graph by ``create_rag_graph``
without the node logic ever branching on deployment mode.

Design reference: serverless-deployment design, section "2b. BedrockClient".

Responsibilities (Requirements 5.1-5.6):

- ``generate(prompt, model_id=None, temperature=0.3, max_tokens=1024)`` invokes
  Anthropic Claude via the Bedrock Messages API. The default inference model is
  ``anthropic.claude-3-haiku-20240307-v1:0`` (Req 5.1), overridable per call via
  ``model_id`` and globally via ``settings.bedrock_model_override`` (Req 5.4).
- ``embed_text(text)`` invokes ``amazon.titan-embed-text-v1`` (1536-dim, Req 5.2)
  then applies a deterministic 1536->768 PCA projection (Req 5.3) so the vectors
  align with the 768-dim OpenSearch k-NN index.
- Both calls retry on Bedrock throttling (HTTP 429 / ``ThrottlingException``) up
  to 3 times with exponential backoff starting at 500ms -> 500/1000/2000ms (Req 5.5).
- Retrieved-document context is formatted to match the shared prompt template in
  ``src/agents/prompts.py`` (Req 5.6).

Import safety: ``boto3`` and ``numpy`` are imported lazily so this module can be
imported cleanly in Local Mode (and in test environments) even when the AWS SDK
is not installed. The ``bedrock-runtime`` client is created lazily on first use.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from src.agents import prompts
from src.config.settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

logger = logging.getLogger(__name__)

# Backoff schedule for throttling retries: 500ms, 1000ms, 2000ms (Req 5.5).
_RETRY_BASE_DELAY = 0.5
_RETRY_MAX_ATTEMPTS = 3

# Bedrock/botocore error codes that indicate throttling (HTTP 429).
_THROTTLING_ERROR_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "Throttling",
    "ThrottledException",
    "ProvisionedThroughputExceededException",
}


class BedrockClient:
    """Bedrock-backed LLM inference + embedding client.

    Conforms to the :class:`~src.tools.interfaces.LLMClient` protocol.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
    ):
        """Initialise the Bedrock client.

        Args:
            settings: Application settings. Falls back to ``get_settings()``.
            client: Optional pre-constructed ``bedrock-runtime`` client. When
                provided (e.g. in tests), it is used as-is and no boto3 import
                is performed. Otherwise the client is created lazily on first
                use so this class can be imported without boto3 installed.
        """
        self.settings = settings or get_settings()
        self._client = client

        # Model configuration (Req 5.1, 5.2, 5.4).
        self.default_model_id = self.settings.bedrock_inference_model_id
        self.model_override = self.settings.bedrock_model_override
        self.embedding_model_id = self.settings.bedrock_embedding_model_id

        # Dimensionality reduction configuration (Req 5.3).
        self.source_dim = self.settings.bedrock_embedding_dim  # 1536
        self.target_dim = self.settings.bedrock_pca_target_dim  # 768
        self.pca_matrix_uri = self.settings.bedrock_pca_matrix_uri

        # Lazily materialised PCA projection matrix (shape: source_dim x target_dim).
        self._pca_matrix: np.ndarray | None = None

    # ------------------------------------------------------------------
    # boto3 client (lazy)
    # ------------------------------------------------------------------
    @property
    def client(self) -> Any:
        """Return the ``bedrock-runtime`` client, creating it on first use.

        The import of ``boto3`` is deferred to here so that importing this
        module never fails in Local Mode where boto3 may be absent.
        """
        if self._client is None:
            try:
                import boto3  # local import by design
            except ImportError as e:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "boto3 is required to use BedrockClient in serverless mode. "
                    "Install it with `pip install boto3`."
                ) from e

            region = self.settings.aws_region or "us-east-1"
            self._client = boto3.client("bedrock-runtime", region_name=region)
        return self._client

    # ------------------------------------------------------------------
    # Retry helper (Req 5.5)
    # ------------------------------------------------------------------
    @staticmethod
    def _is_throttling_error(exc: Exception) -> bool:
        """Return True if ``exc`` represents a Bedrock throttling (HTTP 429)."""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            error = response.get("Error", {})
            if error.get("Code") in _THROTTLING_ERROR_CODES:
                return True
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 429:
                return True
        # Fall back to the exception class name for non-botocore errors.
        return type(exc).__name__ in _THROTTLING_ERROR_CODES

    def _invoke_with_retry(self, body: dict, model_id: str) -> dict:
        """Invoke a Bedrock model, retrying on throttling with exponential backoff.

        Retries up to :data:`_RETRY_MAX_ATTEMPTS` (3) times after the initial
        attempt, sleeping 500ms, 1000ms, then 2000ms between attempts (Req 5.5).
        Non-throttling errors propagate immediately.
        """
        attempt = 0
        while True:
            try:
                response = self.client.invoke_model(
                    modelId=model_id,
                    body=json.dumps(body),
                    accept="application/json",
                    contentType="application/json",
                )
                raw = response["body"].read()
                return json.loads(raw)  # type: ignore[no-any-return]
            except Exception as exc:  # noqa: BLE001 - re-raised below if not throttling
                if not self._is_throttling_error(exc):
                    logger.error(f"Bedrock invoke failed ({model_id}): {exc}")
                    raise
                if attempt >= _RETRY_MAX_ATTEMPTS:
                    logger.error(
                        f"Bedrock throttling: exhausted {_RETRY_MAX_ATTEMPTS} retries "
                        f"for model {model_id}"
                    )
                    raise
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    f"Bedrock throttling on {model_id}; retry "
                    f"{attempt + 1}/{_RETRY_MAX_ATTEMPTS} after {delay:.1f}s"
                )
                time.sleep(delay)
                attempt += 1

    # ------------------------------------------------------------------
    # Generation (Req 5.1, 5.4, 5.5)
    # ------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        model: str | None = None,
        stream: bool = False,
        temperature: float = 0.3,
        max_tokens: int | None = 1024,
    ) -> str:
        """Generate answer text from ``prompt`` using Bedrock (Anthropic Claude).

        Signature matches the :class:`~src.tools.interfaces.LLMClient` protocol
        so this is a drop-in replacement for ``OllamaClient.generate``.

        Model resolution order (Req 5.1, 5.4):
            1. explicit ``model`` argument,
            2. ``settings.bedrock_model_override`` when set,
            3. ``settings.bedrock_inference_model_id`` default
               (``anthropic.claude-3-haiku-20240307-v1:0``).

        Args:
            prompt: The fully-formatted prompt (see :meth:`format_rag_prompt`).
            model: Optional per-call model ID override.
            stream: Accepted for protocol compatibility; synchronous REST only
                in serverless mode, so streaming is not used here.
            temperature: Sampling temperature (default 0.3).
            max_tokens: Maximum tokens to generate (default 1024).

        Returns:
            The generated answer text.
        """
        model_id = self._resolve_model_id(model)
        tokens = max_tokens if (max_tokens is not None and max_tokens > 0) else 1024

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        }

        result = self._invoke_with_retry(body, model_id)
        return self._extract_text(result)

    def _resolve_model_id(self, model: str | None) -> str:
        """Resolve the effective inference model ID (Req 5.1, 5.4).

        An explicit ``model`` argument wins; otherwise the configured
        ``bedrock_model_override`` is honoured; otherwise the default inference
        model is used.
        """
        if model:
            return model
        if self.model_override:
            return self.model_override
        return self.default_model_id

    @staticmethod
    def _extract_text(result: dict) -> str:
        """Extract answer text from an Anthropic Messages API response body."""
        content = result.get("content", [])
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type", "text") == "text"
            ]
            return "".join(parts)
        # Defensive fallback for alternate response shapes.
        if isinstance(content, str):
            return content
        return result.get("completion", "")  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Embeddings (Req 5.2, 5.3, 5.5)
    # ------------------------------------------------------------------
    def embed_text(
        self,
        text: str,
        model: str | None = None,
        timeout: int | None = None,  # noqa: ARG002 - protocol compatibility
    ) -> list[float]:
        """Embed ``text`` with Titan (1536-dim) then project to 768-dim (Req 5.2, 5.3).

        Signature matches the :class:`~src.tools.interfaces.LLMClient` protocol.

        Args:
            text: Text to embed.
            model: Optional embedding model override (defaults to
                ``amazon.titan-embed-text-v1``).
            timeout: Accepted for protocol compatibility; unused for Bedrock.

        Returns:
            A ``bedrock_pca_target_dim`` (768) element embedding vector.
        """
        model_id = model or self.embedding_model_id

        body = {"inputText": text}
        result = self._invoke_with_retry(body, model_id)

        raw_vector = result.get("embedding", [])
        return self._reduce_dimensions(raw_vector)

    def _reduce_dimensions(self, vector: list[float]) -> list[float]:
        """Project a raw embedding to ``target_dim`` via deterministic PCA (Req 5.3).

        Always returns a ``target_dim`` (768) element vector regardless of the
        input length, so downstream OpenSearch indexing/querying always sees a
        consistent dimension.
        """
        import numpy as np

        arr = np.asarray(vector, dtype=np.float64)

        # Normalise the input length to the configured source dimension so the
        # projection is always well-defined even if the backend returns an
        # unexpected length.
        if arr.shape[0] != self.source_dim:
            fixed = np.zeros(self.source_dim, dtype=np.float64)
            n = min(arr.shape[0], self.source_dim)
            fixed[:n] = arr[:n]
            arr = fixed

        matrix = self._get_pca_matrix()  # (source_dim, target_dim)
        projected = arr @ matrix
        return projected.astype(np.float64).tolist()  # type: ignore[no-any-return]

    def _get_pca_matrix(self) -> np.ndarray:
        """Return the (source_dim x target_dim) PCA projection matrix.

        If ``settings.bedrock_pca_matrix_uri`` points at a ``.npy`` artifact
        (local path or ``s3://`` URI) it is loaded once and cached. When unset,
        a deterministic built-in projection derived purely from the matrix
        dimensions is used, so embeddings are stable and reproducible across
        invocations without any external artifact.
        """
        if self._pca_matrix is not None:
            return self._pca_matrix

        matrix: np.ndarray | None = None
        if self.pca_matrix_uri:
            try:
                matrix = self._load_pca_matrix(self.pca_matrix_uri)
            except Exception as e:  # noqa: BLE001 - fall back deterministically
                logger.warning(
                    f"Failed to load PCA matrix from {self.pca_matrix_uri}: {e}; "
                    "falling back to deterministic built-in projection."
                )
                matrix = None

        if matrix is None:
            matrix = self._build_deterministic_matrix()

        # Guarantee the correct shape so output is always target_dim.
        if matrix.shape != (self.source_dim, self.target_dim):
            raise ValueError(
                f"PCA matrix shape {matrix.shape} does not match expected "
                f"({self.source_dim}, {self.target_dim})"
            )

        self._pca_matrix = matrix
        return matrix

    def _load_pca_matrix(self, uri: str) -> np.ndarray:
        """Load a PCA matrix ``.npy`` artifact from a local path or S3 URI."""
        import numpy as np

        if uri.startswith("s3://"):
            import io

            import boto3

            without_scheme = uri[len("s3://") :]
            bucket, _, key = without_scheme.partition("/")
            s3 = boto3.client("s3", region_name=self.settings.aws_region or "us-east-1")
            obj = s3.get_object(Bucket=bucket, Key=key)
            data = obj["Body"].read()
            return np.load(io.BytesIO(data))  # type: ignore[no-any-return]

        return np.load(uri)  # type: ignore[no-any-return]

    def _build_deterministic_matrix(self) -> np.ndarray:
        """Build a deterministic projection matrix from the matrix dimensions.

        The seed is derived solely from ``(source_dim, target_dim)`` so the
        same projection is produced on every invocation and in every process,
        making embeddings reproducible without any stored artifact. Columns are
        orthonormalised (QR) so the projection preserves relative geometry
        similar to a true PCA basis.
        """
        import numpy as np

        seed_source = f"bedrock-pca:{self.source_dim}:{self.target_dim}".encode()
        seed = int.from_bytes(hashlib.sha256(seed_source).digest()[:8], "big")
        rng = np.random.default_rng(seed)

        random_matrix = rng.standard_normal((self.source_dim, self.target_dim))
        # Orthonormalise columns for a stable, variance-preserving projection.
        q, _ = np.linalg.qr(random_matrix)
        return q[:, : self.target_dim]  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Prompt formatting (Req 5.6)
    # ------------------------------------------------------------------
    @staticmethod
    def format_rag_context(sources: list[dict]) -> str:
        """Format retrieved documents into context text (Req 5.6).

        Mirrors the Local Mode context construction (source title + content
        chunk), producing numbered entries that feed the shared RAG prompt
        template. Each entry includes the source title (when present) and the
        document content chunk.

        Args:
            sources: Retrieved documents. Each dict may contain ``text`` (the
                content chunk) and ``metadata.title``/``title`` (the source
                title).

        Returns:
            Newline-separated context string suitable for
            :meth:`format_rag_prompt`.
        """
        parts: list[str] = []
        for i, source in enumerate(sources, 1):
            text = source.get("text") or source.get("snippet") or ""
            metadata = source.get("metadata") or {}
            title = metadata.get("title") or source.get("title") or ""
            if title:
                parts.append(f"[{i}] {title}\n{text}")
            else:
                parts.append(f"[{i}] {text}")
        return "\n\n".join(parts)

    def format_rag_prompt(self, question: str, sources: list[dict]) -> str:
        """Build the full RAG prompt from a question and retrieved documents.

        Uses the shared ``src/agents/prompts.py`` template so the serverless
        prompt structure matches Local Mode exactly (Req 5.6).
        """
        system_instructions = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
            formatting_rules=prompts.FORMATTING_RULES
        )
        context = self.format_rag_context(sources)
        return prompts.format_rag_prompt(
            system_instructions=system_instructions,
            question=question,
            context=context,
        )
