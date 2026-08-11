"""Tests for environment-backed configuration."""

from nexagent.config import Settings


def test_settings_default_to_the_v0_1_ollama_model(monkeypatch) -> None:
    monkeypatch.delenv("NEXAGENT_OLLAMA_MODEL", raising=False)

    assert Settings.from_environment().ollama_model == "qwen3.5:2b-q4_K_M"


def test_settings_reads_non_secret_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("NEXAGENT_ENVIRONMENT", "test")
    monkeypatch.setenv("NEXAGENT_DEBUG", "true")
    monkeypatch.setenv("NEXAGENT_OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("NEXAGENT_OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("NEXAGENT_OLLAMA_TIMEOUT_SECONDS", "12.5")

    settings = Settings.from_environment()

    assert settings.environment == "test"
    assert settings.debug is True
    assert settings.ollama_base_url == "http://ollama.test"
    assert settings.ollama_model == "test-model"
    assert settings.ollama_timeout_seconds == 12.5
