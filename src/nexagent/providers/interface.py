"""Small, provider-agnostic chat contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChatMessage:
    """A single chat message supplied to a model provider."""

    role: str
    content: str


@runtime_checkable
class ModelProvider(Protocol):
    """Contract for a provider that completes a sequence of chat messages."""

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        """Return the provider's text response."""
