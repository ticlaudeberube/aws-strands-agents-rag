from __future__ import annotations

from typing import Any

import pytest

from src.agents.rag_routing import _generate_from_sources, route_rag_query
from src.agents.bedrock_guardrails import (
    apply_bedrock_input_guardrail,
    apply_bedrock_output_guardrail,
    get_bedrock_guardrail_config,
)
from src.config.settings import Settings
from src.tools.bedrock_client import BedrockClient


class _FakeBedrockRuntime:
    def __init__(
        self,
        guardrail_response: dict[str, Any] | None = None,
        input_guardrail_response: dict[str, Any] | None = None,
    ) -> None:
        self.converse_request: dict[str, Any] | None = None
        self.guardrail_request: dict[str, Any] | None = None
        self.guardrail_requests: list[dict[str, Any]] = []
        self.guardrail_response = guardrail_response or {
            "action": "NONE",
            "outputs": [{"text": "Guardrail-evaluated answer"}],
        }
        self.input_guardrail_response = input_guardrail_response or {
            "action": "NONE",
            "outputs": [],
        }

    def converse(self, **request: Any) -> dict[str, Any]:
        self.converse_request = request
        return {
            "output": {
                "message": {
                    "content": [{"text": "Generated answer"}],
                }
            }
        }

    def apply_guardrail(self, **request: Any) -> dict[str, Any]:
        self.guardrail_request = request
        self.guardrail_requests.append(request)
        if request["source"] == "INPUT":
            return self.input_guardrail_response
        return self.guardrail_response


def _guardrail_settings() -> Settings:
    return Settings(
        DEPLOYMENT_MODE="serverless",
        BEDROCK_GUARDRAIL_ID="guardrail-id",
        BEDROCK_GUARDRAIL_VERSION="1",
    )


def test_guardrail_settings_must_be_configured_as_a_pair() -> None:
    with pytest.raises(ValueError, match="must be set together"):
        Settings(DEPLOYMENT_MODE="serverless", BEDROCK_GUARDRAIL_ID="guardrail-id")


def test_converse_guardrail_config_is_enabled_with_trace_disabled() -> None:
    settings = _guardrail_settings()
    runtime = _FakeBedrockRuntime()
    client = BedrockClient(settings=settings, client=runtime)

    client.generate("RAG prompt")

    assert runtime.converse_request is not None
    assert runtime.converse_request["guardrailConfig"] == {
        "guardrailIdentifier": "guardrail-id",
        "guardrailVersion": "1",
        "trace": "disabled",
    }


def test_guardrails_are_not_added_in_local_mode() -> None:
    settings = Settings(DEPLOYMENT_MODE="local")
    runtime = _FakeBedrockRuntime()
    client = BedrockClient(settings=settings, client=runtime)

    client.generate("Local test prompt")

    assert runtime.converse_request is not None
    assert "guardrailConfig" not in runtime.converse_request
    assert runtime.guardrail_request is None


def test_rag_generation_applies_output_guardrail_with_query_and_sources() -> None:
    settings = _guardrail_settings()
    runtime = _FakeBedrockRuntime()
    client = BedrockClient(settings=settings, client=runtime)

    answer = _generate_from_sources(
        llm=client,
        question="What is HNSW?",
        sources=[{"text": "HNSW is a graph-based vector index."}],
        temperature=0.1,
        max_tokens=128,
    )

    assert answer == "Guardrail-evaluated answer"
    assert runtime.guardrail_request is not None
    assert runtime.guardrail_request["source"] == "OUTPUT"
    content = runtime.guardrail_request["content"]
    assert content[0]["text"]["qualifiers"] == ["query"]
    assert content[0]["text"]["text"] == "What is HNSW?"
    assert content[1]["text"]["qualifiers"] == ["guard_content"]
    assert content[2]["text"]["qualifiers"] == ["grounding_source"]


def test_input_guardrail_anonymizes_query_before_routing() -> None:
    runtime = _FakeBedrockRuntime(
        input_guardrail_response={
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "Contact {EMAIL} about vector search."}],
            "assessments": [
                {
                    "sensitiveInformationPolicy": {
                        "piiEntities": [{"type": "EMAIL", "action": "ANONYMIZED"}]
                    }
                }
            ],
        }
    )
    screened, blocked, _ = apply_bedrock_input_guardrail(
        _guardrail_settings(),
        query="Contact user@example.com about vector search.",
        bedrock_runtime_client=runtime,
    )

    assert screened == "Contact {EMAIL} about vector search."
    assert blocked is False
    assert runtime.guardrail_request is not None
    assert runtime.guardrail_request["source"] == "INPUT"


def test_input_guardrail_blocks_before_semantic_cache_lookup() -> None:
    runtime = _FakeBedrockRuntime(
        input_guardrail_response={
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "I cannot process this request."}],
            "assessments": [{"topicPolicy": {"topics": [{"action": "BLOCKED"}]}}],
        }
    )
    client = BedrockClient(settings=_guardrail_settings(), client=runtime)

    class _RecordingLLM:
        def screen_input(self, query: str) -> tuple[str, bool]:
            return client.screen_input(query)

        def embed_text(self, _text: str) -> list[float]:
            raise AssertionError("Blocked input must not be embedded.")

        def generate(self, *_args: Any, **_kwargs: Any) -> str:
            raise AssertionError("Blocked input must not be generated.")

    class _RecordingSemanticCache:
        search_called = False

        def search_semantic_cache(self, **_kwargs: Any) -> dict[str, Any] | None:
            self.search_called = True
            return None

    semantic_cache = _RecordingSemanticCache()
    result = route_rag_query(
        "off-topic query",
        llm=_RecordingLLM(),
        vector_store=object(),
        cache=None,
        semantic_cache=semantic_cache,
        kb_index="rag-kb",
    )

    assert result.answer == "I cannot process this request."
    assert result.tier_used == "guardrail"
    assert semantic_cache.search_called is False


def test_anonymized_input_is_used_for_cache_lookup() -> None:
    runtime = _FakeBedrockRuntime(
        input_guardrail_response={
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "Contact {EMAIL} about vector search."}],
            "assessments": [
                {
                    "sensitiveInformationPolicy": {
                        "piiEntities": [{"type": "EMAIL", "action": "ANONYMIZED"}]
                    }
                }
            ],
        }
    )
    client = BedrockClient(settings=_guardrail_settings(), client=runtime)
    embedded_queries: list[str] = []

    class _RecordingLLM:
        def screen_input(self, query: str) -> tuple[str, bool]:
            return client.screen_input(query)

        def embed_text(self, text: str) -> list[float]:
            embedded_queries.append(text)
            return [0.1, 0.2]

        def generate(self, *_args: Any, **_kwargs: Any) -> str:
            raise AssertionError("A semantic cache hit should not generate.")

    class _RecordingSemanticCache:
        queried_questions: list[str] = []

        def search_semantic_cache(self, question: str, **_kwargs: Any) -> dict[str, Any]:
            self.queried_questions.append(question)
            return {"response": "Cached answer", "similarity": 0.99, "sources": []}

    semantic_cache = _RecordingSemanticCache()
    result = route_rag_query(
        "Contact user@example.com about vector search.",
        llm=_RecordingLLM(),
        vector_store=object(),
        cache=None,
        semantic_cache=semantic_cache,
        kb_index="rag-kb",
    )

    assert result.answer == "Cached answer"
    assert embedded_queries == ["Contact {EMAIL} about vector search."]
    assert semantic_cache.queried_questions == ["Contact {EMAIL} about vector search."]
    assert runtime.guardrail_requests[0]["source"] == "INPUT"


@pytest.mark.parametrize(
    ("guardrail_response", "expected_answer"),
    [
        (
            {"action": "NONE", "outputs": [{"text": "Guardrail-evaluated answer"}]},
            "Guardrail-evaluated answer",
        ),
        (
            {
                "action": "GUARDRAIL_INTERVENED",
                "outputs": [{"text": "Cached answer blocked by policy."}],
            },
            "Cached answer blocked by policy.",
        ),
    ],
)
def test_cached_answer_is_checked_against_query_and_cached_sources(
    guardrail_response: dict[str, Any],
    expected_answer: str,
) -> None:
    runtime = _FakeBedrockRuntime(guardrail_response=guardrail_response)
    client = BedrockClient(settings=_guardrail_settings(), client=runtime)

    class _CachedAnswerLLM:
        bedrock_guardrails_enabled = True

        def embed_text(self, _text: str) -> list[float]:
            return [0.1, 0.2]

        def apply_output_guardrail(
            self, question: str, answer: str, sources: list[dict[str, Any]]
        ) -> str:
            return client.apply_output_guardrail(question, answer, sources)

    class _CachedAnswerSemanticCache:
        def search_semantic_cache(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "response": "Cached answer",
                "similarity": 0.99,
                "sources": [{"text": "Cached grounding source."}],
            }

    result = route_rag_query(
        "What is HNSW?",
        llm=_CachedAnswerLLM(),
        vector_store=object(),
        cache=None,
        semantic_cache=_CachedAnswerSemanticCache(),
        kb_index="rag-kb",
    )

    assert result.answer == expected_answer
    assert result.cache_hit is True
    assert runtime.guardrail_request is not None
    assert runtime.guardrail_request["source"] == "OUTPUT"
    content = runtime.guardrail_request["content"]
    assert content[0]["text"] == {"text": "What is HNSW?", "qualifiers": ["query"]}
    assert content[1]["text"] == {
        "text": "Cached answer",
        "qualifiers": ["guard_content"],
    }
    assert content[2]["text"] == {
        "text": "Cached grounding source.",
        "qualifiers": ["grounding_source"],
    }


def test_cached_answer_without_grounding_refuses_without_output_check() -> None:
    runtime = _FakeBedrockRuntime()
    client = BedrockClient(settings=_guardrail_settings(), client=runtime)

    class _CachedAnswerLLM:
        bedrock_guardrails_enabled = True

        def embed_text(self, _text: str) -> list[float]:
            return [0.1, 0.2]

        def apply_output_guardrail(
            self, question: str, answer: str, sources: list[dict[str, Any]]
        ) -> str:
            return client.apply_output_guardrail(question, answer, sources)

    class _UnGroundedSemanticCache:
        def search_semantic_cache(self, **_kwargs: Any) -> dict[str, Any]:
            return {"response": "Cached answer", "similarity": 0.99, "sources": []}

    result = route_rag_query(
        "What is HNSW?",
        llm=_CachedAnswerLLM(),
        vector_store=object(),
        cache=None,
        semantic_cache=_UnGroundedSemanticCache(),
        kb_index="rag-kb",
    )

    assert result.answer.startswith("I couldn't find usable source information")
    assert result.cache_hit is True
    assert result.grounding_score == 0.0
    assert runtime.guardrail_request is None


def test_intervened_output_uses_guardrail_message() -> None:
    response = {
        "action": "GUARDRAIL_INTERVENED",
        "outputs": [{"text": "I cannot provide that response."}],
    }
    final_text, blocked, _ = apply_bedrock_output_guardrail(
        _guardrail_settings(),
        query="Question",
        answer="Unsafe or ungrounded answer",
        source_chunks=["Trusted source"],
        bedrock_runtime_client=_FakeBedrockRuntime(response),
    )

    assert final_text == "I cannot provide that response."
    assert blocked is True


def test_apply_guardrail_failure_does_not_silently_return_answer() -> None:
    class _FailingRuntime(_FakeBedrockRuntime):
        def apply_guardrail(self, **request: Any) -> dict[str, Any]:
            raise RuntimeError("guardrail unavailable")

    with pytest.raises(RuntimeError, match="guardrail unavailable"):
        apply_bedrock_output_guardrail(
            _guardrail_settings(),
            query="Question",
            answer="Answer",
            source_chunks=["Source"],
            bedrock_runtime_client=_FailingRuntime(),
        )


def test_guardrail_config_is_empty_when_disabled() -> None:
    assert get_bedrock_guardrail_config(Settings(DEPLOYMENT_MODE="local")) == {}
