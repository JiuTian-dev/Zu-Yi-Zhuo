import asyncio
import json

import pytest

from app.sources import (
    HttpCandidateSource,
    HttpContentSignalSource,
    HttpPersonalContextSource,
    CandidateSourceError,
)
from app.sources.base import ContentSignalSourceError, PersonalContextSourceError
import app.sources.http as http_sources


class _Response:
    status = 200

    def __init__(self, payload: object):
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int = -1):
        if not self._body:
            return b""
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


def _candidate(identifier: str = "p1") -> dict:
    return {
        "participant_id": identifier,
        "display_name": identifier,
        "role": "产品",
        "declared_position": "先验证价值",
    }


def _signal(identifier: str = "s1") -> dict:
    return {
        "signal_id": identifier,
        "content_type": "question",
        "title": "如何验证价值？",
        "excerpt": "问题还有未完成部分。",
        "source_ref": "authorized:question:1",
        "author_id": "u1",
        "author_name": "u1",
        "visibility": "public",
    }


def _private_signal(identifier: str = "s1") -> dict:
    return {
        "signal_id": identifier,
        "owner_id": "alice",
        "content_type": "favorite",
        "title": "长期创作",
        "excerpt": "收藏的私密上下文。",
        "source_ref": "authorized:favorite:1",
        "visibility": "private",
    }


def test_http_candidate_source_sends_bearer_token_and_normalizes_payload(monkeypatch) -> None:
    seen = {}

    def fake_urlopen(request, *, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return _Response({"candidates": [_candidate("p1"), _candidate("p2")]})

    monkeypatch.setattr(http_sources, "urlopen", fake_urlopen)
    source = HttpCandidateSource("https://adapter.example/candidates", token="secret-token")
    rows = asyncio.run(source.search(query="Agent", limit=1))

    assert [row.participant_id for row in rows] == ["p1"]
    assert seen["request"].get_header("Authorization") == "Bearer secret-token"
    assert seen["request"].get_header("Content-type") == "application/json"
    assert seen["timeout"] == 5.0


def test_http_content_and_personal_sources_use_their_scoped_contracts(monkeypatch) -> None:
    requests = []
    payloads = [
        {"signals": [_signal()]},
        {"signals": [_private_signal()]},
    ]

    def fake_urlopen(request, *, timeout):
        requests.append(json.loads(request.data.decode("utf-8")))
        return _Response(payloads.pop(0))

    monkeypatch.setattr(http_sources, "urlopen", fake_urlopen)
    content = HttpContentSignalSource("https://adapter.example/content")
    personal = HttpPersonalContextSource("https://adapter.example/personal")

    public_rows = asyncio.run(content.search(query="Agent", limit=1))
    private_rows = asyncio.run(personal.search(
        viewer_id="alice", scopes=["favorites"], query="创作", limit=1
    ))

    assert public_rows[0].visibility == "public"
    assert private_rows[0].owner_id == "alice"
    assert requests == [
        {"query": "Agent", "limit": 1},
        {"viewer_id": "alice", "scopes": ["favorites"], "query": "创作", "limit": 1},
    ]


def test_http_sources_fail_closed_without_leaking_token(monkeypatch) -> None:
    def fake_urlopen(request, *, timeout):
        raise OSError("network down")

    monkeypatch.setattr(http_sources, "urlopen", fake_urlopen)
    source = HttpCandidateSource(
        "https://adapter.example/candidates", token="secret-token"
    )
    with pytest.raises(CandidateSourceError, match="request failed") as error:
        asyncio.run(source.search(query="Agent", limit=1))
    assert "secret-token" not in str(error.value)

    content = HttpContentSignalSource("https://adapter.example/content")
    with pytest.raises(ContentSignalSourceError, match="request failed"):
        asyncio.run(content.search(query="Agent", limit=1))
    personal = HttpPersonalContextSource("https://adapter.example/personal")
    with pytest.raises(PersonalContextSourceError, match="request failed"):
        asyncio.run(personal.search(
            viewer_id="alice", scopes=["favorites"], query="创作", limit=1
        ))


def test_http_source_requires_https_unless_explicitly_enabled() -> None:
    with pytest.raises(ValueError, match="absolute https URL"):
        HttpCandidateSource("http://localhost:9000/source")
    assert HttpCandidateSource(
        "http://localhost:9000/source", allow_insecure_http=True
    ).endpoint.startswith("http://")
