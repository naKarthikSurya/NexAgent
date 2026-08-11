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

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            environment=os.getenv("NEXAGENT_ENVIRONMENT", "development"),
            debug=os.getenv("NEXAGENT_DEBUG", "false").lower() == "true",
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings.from_environment()
