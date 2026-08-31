import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.domain import PersonalContextSignal
from app.sources import CommandPersonalContextSource, PersonalContextSourceError


def _signal(owner_id: str, signal_id: str = "s1") -> dict[str, str]:
    return {
        "signal_id": signal_id,
        "owner_id": owner_id,
        "content_type": "favorite",
        "title": "如何重新找回创造欲",
        "excerpt": "我收藏过关于长期创造和休息的讨论。",
        "source_ref": "authorized:favorite:1",
        "private_stance": "我想保留长期创作时间",
        "visibility": "private",
    }


class _Source:
    def __init__(self, signals):
        self.signals = signals
        self.calls = []

    async def search(self, *, viewer_id: str, query: str, limit: int):
        self.calls.append((viewer_id, query, limit))
        return self.signals[:limit]


class _HangingSource:
    async def search(self, *, viewer_id: str, query: str, limit: int):
        await asyncio.sleep(0.2)
        return []


def test_personal_context_preview_is_viewer_scoped_and_ephemeral() -> None:
    source = _Source([_signal("alice")])
    client = TestClient(create_app(personal_context_source=source))

    response = client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "长期创作", "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["viewer_id"] == "alice"
    assert payload["signals"][0]["owner_id"] == "alice"
    assert payload["signals"][0]["private_stance"] == "我想保留长期创作时间"
    assert payload["themes"]
    assert source.calls == [("alice", "长期创作", 1)]
    assert not hasattr(client.app.state.repository, "_personal_context")


def test_personal_context_source_is_explicitly_unavailable_or_bounded() -> None:
    missing = TestClient(create_app()).post(
        "/personal-context/source-preview?viewer_id=alice", json={"query": "Q"}
    )
    assert missing.status_code == 503

    timed_out = TestClient(create_app(
        personal_context_source=_HangingSource(),
        personal_context_source_timeout_seconds=0.01,
    )).post("/personal-context/source-preview?viewer_id=alice", json={"query": "Q"})
    assert timed_out.status_code == 502
    assert timed_out.json() == {"detail": "personal context source timed out"}


def test_personal_context_rejects_owner_mismatch_and_invalid_output() -> None:
    mismatch = TestClient(create_app(personal_context_source=_Source([_signal("bob")]))).post(
        "/personal-context/source-preview?viewer_id=alice", json={"query": "Q"}
    )
    assert mismatch.status_code == 502
    assert mismatch.json() == {"detail": "personal context source returned invalid signals"}

    duplicate = TestClient(create_app(personal_context_source=_Source([
        _signal("alice", "same"), _signal("alice", "same"),
    ]))).post("/personal-context/source-preview?viewer_id=alice", json={"query": "Q"})
    assert duplicate.status_code == 502


def test_command_personal_source_receives_viewer_without_shell() -> None:
    script = (
        "import json,sys; request=json.load(sys.stdin); "
        "print(json.dumps({'signals':[{'signal_id':'s1','owner_id':request['viewer_id'],"
        "'content_type':'follow','title':'长期学习','excerpt':'我的关注',"
        "'source_ref':'authorized:follow:1','visibility':'private'}]}))"
    )
    source = CommandPersonalContextSource([sys.executable, "-c", script])

    signals = asyncio.run(source.search(viewer_id="alice", query="学习", limit=2))

    assert signals[0].owner_id == "alice"
    assert signals[0].content_type == "follow"


def test_command_personal_source_fails_closed_on_invalid_output() -> None:
    source = CommandPersonalContextSource([sys.executable, "-c", "print('not-json')"])
    with pytest.raises(PersonalContextSourceError, match="invalid JSON"):
        asyncio.run(source.search(viewer_id="alice", query="Q", limit=2))


def test_personal_context_validates_positive_timeout() -> None:
    with pytest.raises(ValueError, match="positive"):
        create_app(personal_context_source_timeout_seconds=0)
