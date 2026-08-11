"""Ollama implementation of the local model-provider contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from nexagent.config import Settings
from nexagent.providers.errors import ProviderResponseError, ProviderUnavailableError
from nexagent.providers.interface import ChatMessage


class OllamaProvider:
    """Send non-streaming chat requests to a locally running Ollama service."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._chat_url = f"{self._base_url}/api/chat"
        self._model = settings.ollama_model
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=settings.ollama_timeout_seconds,
        )

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        """Return a completed response from the configured Ollama model."""

        try:
            response = self._client.post(
                self._chat_url,
                json={
                    "model": self._model,
                    "messages": [message.__dict__ for message in messages],
                    "stream": False,
                },
            )
            response.raise_for_status()
        except httpx.RequestError as error:
            raise ProviderUnavailableError(
                f"Ollama is unavailable at {self._base_url}. Start Ollama and verify "
                "NEXAGENT_OLLAMA_BASE_URL."
            ) from error
        except httpx.HTTPStatusError as error:
            raise ProviderResponseError(
                f"Ollama returned HTTP {error.response.status_code}. Verify model "
                f"'{self._model}' is installed and available."
            ) from error

        return self._response_content(response.json())

    @staticmethod
    def _response_content(payload: dict[str, Any]) -> str:
        try:
            content = payload["message"]["content"]
        except (KeyError, TypeError) as error:
            raise ProviderResponseError(
                "Ollama returned an unexpected chat response. Expected message.content."
            ) from error

        if not isinstance(content, str):
            raise ProviderResponseError(
                "Ollama returned an unexpected chat response. message.content must be text."
            )

        return content
