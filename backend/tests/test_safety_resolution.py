import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed, SafetyLevel
from app.orchestrator import enforce_safety, evaluate_safety


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def _paused(repository: InMemoryTableRepository, table_id: str = "safety-table") -> None:
    repository.create(table_id, "如何让讨论更安全？", [_seed("alice"), _seed("bob")])
    decision = evaluate_safety("我会威胁你。", 1)
    repository.append_safety_state(table_id, enforce_safety(repository.get(table_id), decision))


def _moderator(request) -> str | None:
    return request.headers.get("x-moderator-id")


def test_safety_resolution_requires_configured_moderator_and_resumes() -> None:
    repository = InMemoryTableRepository()
    _paused(repository)
    unconfigured = TestClient(create_app(repository))
    payload = {"action": "resume", "reason": "审核确认属于误报"}
    assert unconfigured.post("/tables/safety-table/safety/resolve", json=payload).status_code == 503

    client = TestClient(create_app(repository, moderator_resolver=_moderator))
    assert client.post("/tables/safety-table/safety/resolve", json=payload).status_code == 401
    response = client.post(
        "/tables/safety-table/safety/resolve",
        json=payload,
        headers={"X-Moderator-ID": "mod-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"]["action"] == "resume"
    assert body["resolution"]["moderator_id"] == "mod-1"
    assert body["resolution"]["from_state_version"] == 1
    assert body["resolution"]["state_version"] == 2
    assert body["state"]["conversation"]["safety_level"] == "normal"
    assert body["state"]["conversation"]["risk_flags"]
    assert repository.get("safety-table").agent.status == "active"
    assert len(repository.safety_resolutions("safety-table")) == 1
    audit = client.get(
        "/tables/safety-table/safety/resolutions",
        headers={"X-Moderator-ID": "mod-1"},
    )
    assert audit.status_code == 200
    assert audit.json()[0]["resolution_id"] == body["resolution"]["resolution_id"]


def test_remove_participant_resolves_pause_without_deleting_history() -> None:
    repository = InMemoryTableRepository()
    _paused(repository, "remove-table")
    client = TestClient(create_app(repository, moderator_resolver=_moderator))

    response = client.post(
        "/tables/remove-table/safety/resolve",
        json={
            "action": "remove_participant",
            "participant_id": "alice",
            "reason": "持续越界，移出当前桌",
        },
        headers={"X-Moderator-ID": "mod-2"},
    )

    assert response.status_code == 200
    state = repository.get("remove-table")
    assert set(state.participants) == {"bob"}
    assert state.conversation.safety_level is SafetyLevel.NORMAL
    assert len(repository.turns("remove-table")) == 0
    assert repository.replay("remove-table")[-1].version == 2
    assert repository.safety_resolutions("remove-table")[0].participant_id == "alice"


def test_safety_resolution_broadcasts_public_event_to_connected_members() -> None:
    repository = InMemoryTableRepository()
    _paused(repository, "broadcast-safety")
    client = TestClient(create_app(repository, moderator_resolver=_moderator))

    with client.websocket_connect("/ws/tables/broadcast-safety?participant_id=alice") as websocket:
        response = client.post(
            "/tables/broadcast-safety/safety/resolve",
            json={"action": "resume", "reason": "审核完成"},
            headers={"X-Moderator-ID": "mod-3"},
        )
        assert response.status_code == 200
        assert websocket.receive_json() == {
            "type": "safety_resolved",
            "action": "resume",
            "participant_id": None,
            "state_version": 2,
        }
        changed = websocket.receive_json()
        assert changed["type"] == "table_state_changed"
        assert changed["state"]["conversation"]["safety_level"] == "normal"


def test_json_repository_persists_safety_resolutions_and_loads_legacy_files(tmp_path) -> None:
    path = tmp_path / "safety-resolution.json"
    json_repo = JsonTableRepository(path)
    json_repo.create("json-safety", "如何让讨论更安全？", [_seed("alice"), _seed("bob")])
    json_repo.append_safety_state(
        "json-safety",
        enforce_safety(json_repo.get("json-safety"), evaluate_safety("我会威胁你。", 1)),
    )
    json_repo.resolve_safety("json-safety", "resume", "mod-json", "审核完成")

    restored = JsonTableRepository(path)
    assert restored.get("json-safety").conversation.safety_level is SafetyLevel.NORMAL
    assert restored.safety_resolutions("json-safety")[0].moderator_id == "mod-json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tables"]["json-safety"].pop("safety_resolutions")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    legacy = JsonTableRepository(path)
    assert legacy.safety_resolutions("json-safety") == []
