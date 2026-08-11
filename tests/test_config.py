"""Tests for environment-backed configuration."""

from nexagent.config import Settings


def test_settings_reads_non_secret_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("NEXAGENT_ENVIRONMENT", "test")
    monkeypatch.setenv("NEXAGENT_DEBUG", "true")

    settings = Settings.from_environment()

    assert settings.environment == "test"
    assert settings.debug is True
