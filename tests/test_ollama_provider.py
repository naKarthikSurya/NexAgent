"""Tests for the local Ollama provider."""

from __future__ import annotations

import json

import httpx
import pytest

from nexagent.config import Settings
from nexagent.providers.errors import ProviderResponseError, ProviderUnavailableError
from nexagent.providers.interface import ChatMessage, ModelProvider
from nexagent.providers.ollama import OllamaProvider


def test_ollama_provider_posts_chat_request_and_returns_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://ollama.test/api/chat"
        assert json.loads(request.content) == {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        }
        return httpx.Response(200, json={"message": {"content": "Hi"}}, request=request)

    provider = OllamaProvider(
        Settings(ollama_base_url="http://ollama.test", ollama_model="test-model"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert isinstance(provider, ModelProvider)
    assert provider.generate([ChatMessage(role="user", content="Hello")]) == "Hi"


def test_ollama_provider_reports_unavailable_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    provider = OllamaProvider(
        Settings(ollama_base_url="http://127.0.0.1:11434"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderUnavailableError, match="Ollama is unavailable"):
        provider.generate([ChatMessage(role="user", content="Hello")])


def test_ollama_provider_reports_missing_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"}, request=request)

    provider = OllamaProvider(
        Settings(ollama_model="missing-model"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderResponseError, match="missing-model"):
        provider.generate([ChatMessage(role="user", content="Hello")])
