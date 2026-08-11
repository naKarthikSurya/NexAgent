"""Tests for the minimal single-agent runtime."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from nexagent.providers.interface import ChatMessage
from nexagent.runtime import DEFAULT_SYSTEM_PROMPT, SingleAgentRuntime


class MockProvider:
    """Deterministic provider used to inspect runtime requests."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[tuple[ChatMessage, ...]] = []

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(tuple(messages))
        return self.responses.pop(0)


def test_runtime_sends_explicit_system_prompt_and_returns_response() -> None:
    provider = MockProvider(["I can help with that."])
    runtime = SingleAgentRuntime(provider)

    response = runtime.run("Explain this function")

    assert response.content == "I can help with that."
    assert provider.calls == [
        (
            ChatMessage(role="system", content=DEFAULT_SYSTEM_PROMPT),
            ChatMessage(role="user", content="Explain this function"),
        )
    ]
    assert runtime.conversation == (
        ChatMessage(role="user", content="Explain this function"),
        ChatMessage(role="assistant", content="I can help with that."),
    )


def test_runtime_reuses_only_completed_conversation_turns() -> None:
    provider = MockProvider(["First response", "Second response"])
    runtime = SingleAgentRuntime(provider)

    runtime.run("First request")
    runtime.run("Second request")

    assert provider.calls[1] == (
        ChatMessage(role="system", content=DEFAULT_SYSTEM_PROMPT),
        ChatMessage(role="user", content="First request"),
        ChatMessage(role="assistant", content="First response"),
        ChatMessage(role="user", content="Second request"),
    )


def test_runtime_rejects_an_empty_request_without_calling_provider() -> None:
    provider = MockProvider(["Unused"])
    runtime = SingleAgentRuntime(provider)

    with pytest.raises(ValueError, match="must not be empty"):
        runtime.run("   ")

    assert provider.calls == []
