"""Local model-provider integrations."""

from nexagent.providers.interface import ChatMessage, ModelProvider
from nexagent.providers.ollama import OllamaProvider

__all__ = ["ChatMessage", "ModelProvider", "OllamaProvider"]
