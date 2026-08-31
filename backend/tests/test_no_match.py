import json

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed


def _seed(participant_id: str, role: str = "实践者") -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="公开立场",
    )


class _CandidateSource:
    async def search(self, *, query: str, limit: int):
        return [
            _seed("blocked", "研究员"),
            _seed("available", "产品经理"),
        ][:limit]


def test_no_match_is_self_scoped_symmetric_and_idempotent() -> None:
    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository))

    created = client.post("/participants/alice/no-match/bob?viewer_id=alice")
    repeated = client.post("/participants/alice/no-match/bob?viewer_id=alice")

    assert created.status_code == repeated.status_code == 201
    assert created.json() == {
        "participant_id": "alice",
        "blocked_participant_id": "bob",
    }
    assert client.get("/participants/alice/no-match?viewer_id=alice").json() == [created.json()]
    assert repository.is_no_match("bob", "alice") is True
    assert client.get("/participants/alice/no-match?viewer_id=bob").status_code == 403

    assert client.delete("/participants/alice/no-match/bob?viewer_id=alice").status_code == 204
    assert client.delete("/participants/alice/no-match/bob?viewer_id=alice").status_code == 204
    assert repository.is_no_match("alice", "bob") is False


def test_no_match_rejects_self_and_invitation_boundary() -> None:
    repository = InMemoryTableRepository()
    repository.create("safety", "Q", [_seed("alice")])
    client = TestClient(create_app(repository))

    assert client.post("/participants/alice/no-match/alice?viewer_id=alice").status_code == 422
    assert client.post("/participants/alice/no-match/bob?viewer_id=bob").status_code == 403
    assert client.post("/participants/alice/no-match/bob?viewer_id=alice").status_code == 201

    response = client.post(
        "/tables/safety/invitations?inviter_id=alice",
        json={
            "candidate": _seed("bob", "研究员").model_dump(mode="json"),
            "reason": "补充专业视角",
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "participant has disabled matching with this candidate"}


def test_candidate_preview_filters_blocked_candidate_without_mutating_table() -> None:
    repository = InMemoryTableRepository()
    repository.create("preview", "如何落地？", [_seed("alice")])
    repository.set_no_match("alice", "blocked")
    client = TestClient(create_app(repository, candidate_source=_CandidateSource()))

    response = client.post(
        "/tables/preview/candidate-preview?participant_id=alice",
        json={"query": "落地", "limit": 2},
    )

    assert response.status_code == 200
    assert [item["participant_id"] for item in response.json()["candidates"]] == ["available"]
    assert repository.get("preview").version == 0
    assert repository.invitations("preview") == []


def test_json_repository_persists_no_match_and_loads_legacy_snapshot(tmp_path) -> None:
    path = tmp_path / "no-match.json"
    repository = JsonTableRepository(path)
    repository.create("persisted", "Q", [_seed("alice")])
    repository.set_no_match("alice", "bob")

    restored = JsonTableRepository(path)
    assert restored.no_match_preferences("alice")[0].blocked_participant_id == "bob"
    assert restored.is_no_match("bob", "alice") is True

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("no_match")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    legacy = JsonTableRepository(path)
    assert legacy.no_match_preferences("alice") == []


def test_json_repository_rejects_invalid_no_match_snapshot(tmp_path) -> None:
    path = tmp_path / "invalid-no-match.json"
    repository = JsonTableRepository(path)
    repository.create("persisted", "Q", [_seed("alice")])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["no_match"] = {"alice": ["alice"]}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid no_match participant"):
        JsonTableRepository(path)
