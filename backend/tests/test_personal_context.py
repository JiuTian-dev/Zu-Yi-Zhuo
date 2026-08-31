import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import JsonTableRepository
from app.domain import PersonalContextConsent, PersonalContextSignal
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

    async def search(self, *, viewer_id: str, scopes, query: str, limit: int):
        self.calls.append((viewer_id, list(scopes), query, limit))
        return self.signals[:limit]


class _HangingSource:
    async def search(self, *, viewer_id: str, scopes, query: str, limit: int):
        await asyncio.sleep(0.2)
        return []


def test_personal_context_preview_is_viewer_scoped_and_ephemeral() -> None:
    source = _Source([_signal("alice")])
    client = TestClient(create_app(personal_context_source=source))
    consent = client.put(
        "/participants/alice/personal-context/consent?viewer_id=alice",
        json={"scopes": ["favorites", "public_content"]},
    )
    assert consent.status_code == 200

    response = client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "长期创作", "limit": 1, "scopes": ["favorites"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["viewer_id"] == "alice"
    assert payload["signals"][0]["owner_id"] == "alice"
    assert payload["signals"][0]["private_stance"] == "我想保留长期创作时间"
    assert payload["themes"]
    assert source.calls == [("alice", ["favorites"], "长期创作", 1)]
    assert not hasattr(client.app.state.repository, "_personal_context")


def test_personal_context_source_is_explicitly_unavailable_or_bounded() -> None:
    missing_client = TestClient(create_app())
    assert missing_client.put(
        "/participants/alice/personal-context/consent?viewer_id=alice",
        json={"scopes": ["favorites"]},
    ).status_code == 200
    missing = missing_client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "Q", "scopes": ["favorites"]},
    )
    assert missing.status_code == 503

    timed_out_client = TestClient(create_app(
        personal_context_source=_HangingSource(),
        personal_context_source_timeout_seconds=0.01,
    ))
    assert timed_out_client.put(
        "/participants/alice/personal-context/consent?viewer_id=alice",
        json={"scopes": ["favorites"]},
    ).status_code == 200
    timed_out = timed_out_client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "Q", "scopes": ["favorites"]},
    )
    assert timed_out.status_code == 502
    assert timed_out.json() == {"detail": "personal context source timed out"}


def test_personal_context_consent_is_self_scoped_scope_limited_and_reversible() -> None:
    client = TestClient(create_app())
    assert client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "Q", "scopes": ["favorites"]},
    ).status_code == 403
    granted = client.put(
        "/participants/alice/personal-context/consent?viewer_id=alice",
        json={"scopes": ["favorites", "follows"]},
    )
    assert granted.status_code == 200
    assert client.get(
        "/participants/alice/personal-context/consent?viewer_id=alice"
    ).json() == granted.json()
    assert client.get(
        "/participants/alice/personal-context/consent?viewer_id=bob"
    ).status_code == 403
    assert client.put(
        "/participants/alice/personal-context/consent?viewer_id=alice",
        json={"scopes": ["favorites", "favorites"]},
    ).status_code == 422
    assert client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "Q", "scopes": ["profile"]},
    ).status_code == 403
    assert client.delete(
        "/participants/alice/personal-context/consent?viewer_id=alice"
    ).status_code == 204
    assert client.get(
        "/participants/alice/personal-context/consent?viewer_id=alice"
    ).status_code == 404


def test_json_repository_persists_and_revokes_personal_context_consent(tmp_path) -> None:
    path = tmp_path / "personal-consent.json"
    repository = JsonTableRepository(path)
    consent = repository.set_personal_context_consent(
        PersonalContextConsent(viewer_id="alice", scopes=["favorites"])
    )
    assert JsonTableRepository(path).personal_context_consent("alice") == consent
    restored = JsonTableRepository(path)
    assert restored.revoke_personal_context_consent("alice") is True
    assert JsonTableRepository(path).personal_context_consent("alice") is None

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("personal_context_consents")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert JsonTableRepository(path).personal_context_consent("alice") is None


def test_personal_context_rejects_owner_mismatch_and_invalid_output() -> None:
    mismatch_client = TestClient(
        create_app(personal_context_source=_Source([_signal("bob")]))
    )
    assert mismatch_client.put(
        "/participants/alice/personal-context/consent?viewer_id=alice",
        json={"scopes": ["favorites"]},
    ).status_code == 200
    mismatch = mismatch_client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "Q", "scopes": ["favorites"]},
    )
    assert mismatch.status_code == 502
    assert mismatch.json() == {"detail": "personal context source returned invalid signals"}

    duplicate_client = TestClient(create_app(personal_context_source=_Source([
        _signal("alice", "same"), _signal("alice", "same"),
    ])))
    assert duplicate_client.put(
        "/participants/alice/personal-context/consent?viewer_id=alice",
        json={"scopes": ["favorites"]},
    ).status_code == 200
    duplicate = duplicate_client.post(
        "/personal-context/source-preview?viewer_id=alice",
        json={"query": "Q", "scopes": ["favorites"]},
    )
    assert duplicate.status_code == 502


def test_command_personal_source_receives_viewer_without_shell() -> None:
    script = (
        "import json,sys; request=json.load(sys.stdin); "
        "print(json.dumps({'signals':[{'signal_id':'s1','owner_id':request['viewer_id'],"
        "'content_type':'follow','title':'长期学习','excerpt':'我的关注',"
        "'source_ref':'authorized:follow:1','visibility':'private'}]}))"
    )
    source = CommandPersonalContextSource([sys.executable, "-c", script])

    signals = asyncio.run(source.search(
        viewer_id="alice", scopes=["follows"], query="学习", limit=2
    ))

    assert signals[0].owner_id == "alice"
    assert signals[0].content_type == "follow"


def test_command_personal_source_fails_closed_on_invalid_output() -> None:
    source = CommandPersonalContextSource([sys.executable, "-c", "print('not-json')"])
    with pytest.raises(PersonalContextSourceError, match="invalid JSON"):
        asyncio.run(source.search(viewer_id="alice", scopes=["favorites"], query="Q", limit=2))


def test_command_personal_source_timeout_covers_process_start(monkeypatch) -> None:
    async def blocked_start(*args, **kwargs):
        await asyncio.sleep(0.2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", blocked_start)
    source = CommandPersonalContextSource([sys.executable, "-c", "print('{}')"], timeout_seconds=0.01)

    with pytest.raises(PersonalContextSourceError, match="timed out"):
        asyncio.run(source.search(viewer_id="alice", scopes=["favorites"], query="Q", limit=2))


def test_personal_context_validates_positive_timeout() -> None:
    with pytest.raises(ValueError, match="positive"):
        create_app(personal_context_source_timeout_seconds=0)
