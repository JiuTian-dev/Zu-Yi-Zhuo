import pytest

from app.main import _build_provider, _build_source_match_preview_ttl


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


def test_runtime_source_match_preview_ttl_defaults_to_five_minutes(monkeypatch) -> None:
    monkeypatch.delenv("SOURCE_MATCH_PREVIEW_TTL_SECONDS", raising=False)
    assert _build_source_match_preview_ttl() == 300.0


@pytest.mark.parametrize("raw", ["0", "-1", "not-a-number"])
def test_runtime_source_match_preview_ttl_rejects_non_positive_or_invalid_values(monkeypatch, raw) -> None:
    monkeypatch.setenv("SOURCE_MATCH_PREVIEW_TTL_SECONDS", raw)
    with pytest.raises(RuntimeError, match="positive number"):
        _build_source_match_preview_ttl()
