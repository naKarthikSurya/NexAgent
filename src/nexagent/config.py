"""Local application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Configuration loaded from non-secret environment variables."""

    environment: str = "development"
    debug: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:2b-q4_K_M"
    ollama_timeout_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            environment=os.getenv("NEXAGENT_ENVIRONMENT", "development"),
            debug=os.getenv("NEXAGENT_DEBUG", "false").lower() == "true",
            ollama_base_url=os.getenv("NEXAGENT_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("NEXAGENT_OLLAMA_MODEL", "qwen3.5:2b-q4_K_M"),
            ollama_timeout_seconds=float(os.getenv("NEXAGENT_OLLAMA_TIMEOUT_SECONDS", "30")),
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings.from_environment()
