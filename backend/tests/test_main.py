import pytest

from app.main import _build_provider


def test_runtime_provider_defaults_to_deterministic(monkeypatch) -> None:
    monkeypatch.delenv("CONVERSATION_PROVIDER", raising=False)
    assert _build_provider() is None


def test_runtime_provider_rejects_unknown_mode(monkeypatch) -> None:
    monkeypatch.setenv("CONVERSATION_PROVIDER", "not-a-provider")
    with pytest.raises(RuntimeError, match="deterministic, openai"):
        _build_provider()


def test_runtime_openai_mode_fails_clearly_without_credentials(monkeypatch) -> None:
    monkeypatch.setenv("CONVERSATION_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        _build_provider()
