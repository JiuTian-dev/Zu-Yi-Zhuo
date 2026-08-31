import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.sources import CommandContentSignalSource, ContentSignalSourceError


class _Source:
    def __init__(self, signals):
        self.signals = signals
        self.calls = []

    async def search(self, *, query, limit):
        self.calls.append((query, limit))
        return self.signals[:limit]


class _HangingSource:
    async def search(self, *, query, limit):
        await asyncio.sleep(0.2)
        return []


def _signal(signal_id: str, author_id: str, content_type: str = "answer") -> dict:
    return {
        "signal_id": signal_id,
        "content_type": content_type,
        "title": "企业 Agent 如何落地？",
        "excerpt": "试点需要明确责任和验收边界。",
        "source_ref": f"authorized:public:{signal_id}",
        "author_id": author_id,
        "author_name": author_id,
        "author_role": "产品" if author_id == "u1" else "架构师",
        "public_stance": "先验证价值" if author_id == "u1" else "先解决技术边界",
    }


def test_source_opportunity_preview_reuses_detector_and_preserves_public_contract() -> None:
    source = _Source([_signal("s1", "u1", "question"), _signal("s2", "u2")])
    client = TestClient(create_app(content_source=source))

    response = client.post(
        "/opportunities/source-preview",
        json={"query": "企业 Agent 如何落地？", "limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["core_question"] == "企业 Agent 如何落地？"
    assert payload["signal_ids"] == ["s1", "s2"]
    assert {item["participant_id"] for item in payload["candidates"]} == {"u1", "u2"}
    assert source.calls == [("企业 Agent 如何落地？", 2)]


def test_source_opportunity_preview_fails_closed_without_source_or_with_bad_signals() -> None:
    missing = TestClient(create_app()).post(
        "/opportunities/source-preview", json={"query": "Q"}
    )
    assert missing.status_code == 503
    assert missing.json() == {"detail": "content source is not configured"}

    invalid = _Source([{"signal_id": "only-partial"}])
    client = TestClient(create_app(content_source=invalid))
    response = client.post("/opportunities/source-preview", json={"query": "Q"})
    assert response.status_code == 502
    assert response.json() == {"detail": "content source returned invalid signals"}


def test_source_opportunity_preview_times_out_and_rejects_non_positive_timeout() -> None:
    client = TestClient(create_app(
        content_source=_HangingSource(), content_source_timeout_seconds=0.01,
    ))
    response = client.post("/opportunities/source-preview", json={"query": "Q"})
    assert response.status_code == 502
    assert response.json() == {"detail": "content source timed out"}

    try:
        create_app(content_source_timeout_seconds=0)
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("non-positive content source timeout must be rejected")


def test_command_content_signal_source_uses_bounded_json_contract() -> None:
    script = (
        "import json,sys; request=json.load(sys.stdin); "
        "print(json.dumps({'signals':[{'signal_id':'s1','content_type':'answer',"
        "'title':'题目','excerpt':'摘要','source_ref':'source:1','author_id':'u1',"
        "'author_name':'甲'}]}))"
    )
    source = CommandContentSignalSource([sys.executable, "-c", script])

    signals = asyncio.run(source.search(query="企业 Agent", limit=2))

    assert len(signals) == 1
    assert signals[0].signal_id == "s1"


def test_command_content_signal_source_fails_closed_on_bad_json_and_output_limits() -> None:
    invalid = CommandContentSignalSource([sys.executable, "-c", "print('not-json')"])
    try:
        asyncio.run(invalid.search(query="Q", limit=2))
    except ContentSignalSourceError as error:
        assert "invalid JSON" in str(error)
    else:
        raise AssertionError("invalid content source output must fail")

    oversized = CommandContentSignalSource(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100)"],
        max_output_bytes=16,
    )
    try:
        asyncio.run(oversized.search(query="Q", limit=2))
    except ContentSignalSourceError as error:
        assert "too large" in str(error)
    else:
        raise AssertionError("oversized content source output must fail")


def test_command_content_source_timeout_covers_process_start(monkeypatch) -> None:
    async def blocked_start(*args, **kwargs):
        await asyncio.sleep(0.2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", blocked_start)
    source = CommandContentSignalSource([sys.executable, "-c", "print('{}')"], timeout_seconds=0.01)

    with pytest.raises(ContentSignalSourceError, match="timed out"):
        asyncio.run(source.search(query="Q", limit=2))


def test_runtime_content_source_command_is_configured_as_json_argv(monkeypatch) -> None:
    command = [sys.executable, "-c", "import sys; sys.stdout.write('{\"signals\":[]}')"]
    monkeypatch.setenv("CONTENT_SIGNAL_SOURCE_COMMAND", json.dumps(command))

    from app.main import _build_content_source

    source = _build_content_source()
    assert isinstance(source, CommandContentSignalSource)
    assert tuple(command) == source.command
