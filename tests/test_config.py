import pytest

import workflow.config as config


def test_validate_settings_accepts_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "MODEL_PROVIDER", "ollama")

    config.validate_settings()


def test_validate_settings_accepts_gemini_with_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "MODEL_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    config.validate_settings()


def test_validate_settings_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "MODEL_PROVIDER", "unknown")

    with pytest.raises(RuntimeError, match="MODEL_PROVIDER"):
        config.validate_settings()


def test_validate_settings_requires_gemini_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "MODEL_PROVIDER", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        config.validate_settings()
