import logging
from typing import Any

from src.config import Settings

logger = logging.getLogger(__name__)

OUTPUT_GUARDRAIL_BLOCKED_MESSAGE = (
    "I cannot provide a response that violates content or grounding policies."
)
INPUT_GUARDRAIL_BLOCKED_MESSAGE = (
    "I cannot process this request due to safety or topic restrictions."
)


class OutputGuardrailBlocked(Exception):
    """Raised when the OUTPUT Guardrail blocks a generated answer.

    ``message`` is the user-facing refusal. Callers must not retry generation or
    cache the blocked answer.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def apply_bedrock_input_guardrail(
    settings: Settings,
    query: str,
    bedrock_runtime_client: Any | None = None,
) -> tuple[str, bool, dict[str, Any]]:
    """Screen a user query and return any anonymized text before routing."""
    if not settings.use_bedrock_guardrails:
        return query, False, {}

    client = bedrock_runtime_client
    if client is None:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    response = client.apply_guardrail(
        guardrailIdentifier=settings.bedrock_guardrail_id,
        guardrailVersion=settings.bedrock_guardrail_version,
        source="INPUT",
        content=[{"text": {"text": query}}],
    )

    action = response.get("action")
    if action == "NONE":
        return query, False, response
    if action != "GUARDRAIL_INTERVENED":
        raise RuntimeError(f"Bedrock ApplyGuardrail returned unexpected action: {action!r}")

    outputs = response.get("outputs", [])
    output_text = outputs[0].get("text") if outputs else None
    assessments = response.get("assessments", [])
    if _contains_assessment_action(assessments, "BLOCKED"):
        return output_text or INPUT_GUARDRAIL_BLOCKED_MESSAGE, True, response

    if _contains_assessment_action(assessments, "ANONYMIZED") and output_text:
        return output_text, False, response

    raise RuntimeError(
        "Bedrock ApplyGuardrail intervened on input without a recognized block or "
        "anonymization assessment."
    )


def apply_bedrock_output_guardrail(
    settings: Settings,
    query: str,
    answer: str,
    source_chunks: list[str],
    bedrock_runtime_client: Any | None = None,
) -> tuple[str, bool, dict[str, Any]]:
    """Run Bedrock Guardrail contextual grounding & PII check on RAG output (serverless only).

    Returns:
        (final_text, was_blocked, assessment_metadata)
    """
    if not settings.use_bedrock_guardrails:
        return answer, False, {}

    client = bedrock_runtime_client
    if client is None:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    combined_sources = "\n\n".join(source_chunks) if source_chunks else ""
    if combined_sources:
        content: list[dict[str, Any]] = [
            {"text": {"text": query, "qualifiers": ["query"]}},
            {"text": {"text": answer, "qualifiers": ["guard_content"]}},
            {"text": {"text": combined_sources, "qualifiers": ["grounding_source"]}},
        ]
    else:
        # No grounding source: run the non-grounding policies (PII, content)
        # on the answer alone. Contextual grounding needs source and query.
        content = [{"text": {"text": answer}}]
    response = client.apply_guardrail(
        guardrailIdentifier=settings.bedrock_guardrail_id,
        guardrailVersion=settings.bedrock_guardrail_version,
        source="OUTPUT",
        content=content,
    )
    action = response.get("action")
    if action not in {"NONE", "GUARDRAIL_INTERVENED"}:
        raise RuntimeError(f"Bedrock ApplyGuardrail returned unexpected action: {action!r}")
    outputs = response.get("outputs", [])
    output_text = outputs[0].get("text") if outputs else None
    if action == "GUARDRAIL_INTERVENED":
        assessments = response.get("assessments", [])
        # PII anonymization rewrites the answer but is not a block.
        if (
            output_text
            and _contains_assessment_action(assessments, "ANONYMIZED")
            and not _contains_assessment_action(assessments, "BLOCKED")
        ):
            logger.info("[BEDROCK_GUARDRAIL] Output anonymized by guardrail policy")
            return output_text, False, response
        logger.warning("[BEDROCK_GUARDRAIL] Output blocked by guardrail policy")
        return output_text or OUTPUT_GUARDRAIL_BLOCKED_MESSAGE, True, response
    return output_text if output_text is not None else answer, False, response


def _contains_assessment_action(value: Any, action: str) -> bool:
    """Check nested Guardrail assessments for a specific policy action."""
    if isinstance(value, dict):
        return any(
            item == action if key == "action" else _contains_assessment_action(item, action)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_assessment_action(item, action) for item in value)
    return False
