"""Unit tests for the CLI conversation history helper (chatbots/interactive_chat.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CHAT_PATH = Path(__file__).resolve().parent.parent.parent / "chatbots" / "interactive_chat.py"
_spec = importlib.util.spec_from_file_location("interactive_chat", _CHAT_PATH)
assert _spec and _spec.loader
interactive_chat = importlib.util.module_from_spec(_spec)
sys.modules["interactive_chat"] = interactive_chat
_spec.loader.exec_module(interactive_chat)


def test_new_conversation_has_no_turns() -> None:
    assert interactive_chat.ConversationHistory().as_messages() == []


def test_record_exchange_stores_question_then_answer() -> None:
    conversation = interactive_chat.ConversationHistory()

    conversation.record_exchange("What is a vector database?", "A store for embeddings.")

    assert conversation.as_messages() == [
        {"role": "user", "content": "What is a vector database?"},
        {"role": "assistant", "content": "A store for embeddings."},
    ]


def test_turns_accumulate_in_order() -> None:
    conversation = interactive_chat.ConversationHistory()

    conversation.record_exchange("Q1", "A1")
    conversation.record_exchange("Q2", "A2")

    assert [turn["content"] for turn in conversation.as_messages()] == ["Q1", "A1", "Q2", "A2"]


def test_as_messages_returns_a_copy() -> None:
    conversation = interactive_chat.ConversationHistory()
    conversation.record_exchange("Q1", "A1")

    snapshot = conversation.as_messages()
    snapshot.clear()

    assert len(conversation.as_messages()) == 2
