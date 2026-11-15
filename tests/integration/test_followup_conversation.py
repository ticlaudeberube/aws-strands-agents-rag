"""Live follow-up check through the local chat API (ROADMAP item 9).

Runs a two-turn conversation against the real local agent: Ollama for
embeddings and generation, and the local OpenSearch KB. The follow-up must be
answered from the knowledge base, not refused as off-topic. The test is skipped
when either backend is unreachable.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.config.settings import get_settings

COMPLETIONS = "/v1/chat/completions"
FIRST_QUESTION = "What is a vector database?"
FOLLOW_UP = "What can I do with it?"
OFF_TOPIC_MARKER = "I can help with questions about"


def _reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _host_port(url_or_host: str) -> tuple[str, int]:
    trimmed = url_or_host.replace("http://", "").replace("https://", "").rstrip("/")
    host, _, port = trimmed.partition(":")
    return host, int(port) if port else 80


def _backends_available() -> bool:
    settings = get_settings()
    ollama_host, ollama_port = _host_port(settings.ollama_host)
    os_host = settings.opensearch_local_host or "localhost"
    os_port = int(settings.opensearch_local_port or 9200)
    return _reachable(ollama_host, ollama_port) and _reachable(os_host, os_port)


def _content(response: Any) -> str:
    return str(response.json()["choices"][0]["message"]["content"])


@pytest.mark.integration
@pytest.mark.slow
def test_follow_up_is_answered_from_prior_turn() -> None:
    if not _backends_available():
        pytest.skip("Ollama or local OpenSearch is not reachable")

    import api_server

    with TestClient(api_server.app) as client:
        first = client.post(
            COMPLETIONS,
            json={"messages": [{"role": "user", "content": [{"text": FIRST_QUESTION}]}]},
        )
        assert first.status_code == 200
        first_answer = _content(first)

        follow_up = client.post(
            COMPLETIONS,
            json={
                "messages": [
                    {"role": "user", "content": [{"text": FIRST_QUESTION}]},
                    {"role": "assistant", "content": [{"text": first_answer}]},
                    {"role": "user", "content": [{"text": FOLLOW_UP}]},
                ]
            },
        )

    assert follow_up.status_code == 200
    answer = _content(follow_up)
    assert answer.strip()
    assert OFF_TOPIC_MARKER not in answer
