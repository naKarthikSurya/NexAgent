"""Minimal single-agent runtime for local provider completions."""

from __future__ import annotations

from dataclasses import dataclass

from nexagent.config import Settings
from nexagent.providers.interface import ChatMessage, ModelProvider
from nexagent.providers.ollama import OllamaProvider

DEFAULT_SYSTEM_PROMPT = (
    "You are NexAgent, a local coding assistant. "
    "Answer the user's request directly and clearly. "
    "You have no tools in this runtime: do not claim to inspect files, run commands, "
    "or make changes."
)


@dataclass(frozen=True)
class RuntimeResponse:
    """The text returned by one single-agent runtime turn."""

    content: str


class SingleAgentRuntime:
    """Maintain a minimal in-memory conversation around a single provider."""

    def __init__(self, provider: ModelProvider, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        self._provider = provider
        self._system_prompt = system_prompt
        self._conversation: list[ChatMessage] = []

    @property
    def conversation(self) -> tuple[ChatMessage, ...]:
        """Return completed user and assistant messages retained for this runtime."""

        return tuple(self._conversation)

    def run(self, user_request: str) -> RuntimeResponse:
        """Send a user request to the provider and retain the completed exchange."""

        request = user_request.strip()
        if not request:
            raise ValueError("A user request must not be empty.")

        user_message = ChatMessage(role="user", content=request)
        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            *self._conversation,
            user_message,
        ]
        assistant_message = ChatMessage(
            role="assistant",
            content=self._provider.generate(messages),
        )
        self._conversation.extend((user_message, assistant_message))

        return RuntimeResponse(content=assistant_message.content)


def create_runtime(settings: Settings) -> SingleAgentRuntime:
    """Create the default runtime with the configured local Ollama provider."""

    return SingleAgentRuntime(OllamaProvider(settings))
