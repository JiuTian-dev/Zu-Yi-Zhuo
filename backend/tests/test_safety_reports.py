import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed, SafetyReport


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def _client(table_id: str = "report-table") -> tuple[TestClient, InMemoryTableRepository]:
    repository = InMemoryTableRepository()
    repository.create(table_id, "如何让讨论更安全？", [_seed("alice"), _seed("bob")])
    return TestClient(create_app(repository)), repository


def _payload(description: str = "对方持续发送人身攻击") -> dict[str, str]:
    return {
        "report_id": "report-1",
        "target_participant_id": "bob",
        "category": "harassment",
        "description": description,
    }


def test_report_is_idempotent_private_and_does_not_mutate_table() -> None:
    client, repository = _client()

    first = client.post("/tables/report-table/safety-reports?reporter_id=alice", json=_payload())
    duplicate = client.post("/tables/report-table/safety-reports?reporter_id=alice", json=_payload())
    conflict = client.post(
        "/tables/report-table/safety-reports?reporter_id=alice",
        json=_payload("换一段相同 report_id 的内容"),
    )

    assert first.status_code == duplicate.status_code == 201
    assert first.json() == duplicate.json()
    assert conflict.status_code == 409
    assert client.get("/tables/report-table/safety-reports?reporter_id=alice").json() == [first.json()]
    assert client.get("/tables/report-table/safety-reports?reporter_id=bob").json() == []
    assert repository.get("report-table").version == 0
    assert repository.turns("report-table") == []


def test_report_identity_and_target_boundaries_are_server_side() -> None:
    client, _repository = _client("report-guards")

    assert client.post(
        "/tables/report-guards/safety-reports?reporter_id=unknown", json=_payload()
    ).status_code == 403
    unknown_target = _payload()
    unknown_target["target_participant_id"] = "nobody"
    assert client.post(
        "/tables/report-guards/safety-reports?reporter_id=alice", json=unknown_target
    ).status_code == 404
    self_report = _payload()
    self_report["target_participant_id"] = "alice"
    assert client.post(
        "/tables/report-guards/safety-reports?reporter_id=alice", json=self_report
    ).status_code == 409
    assert client.get("/tables/report-guards/safety-reports?reporter_id=unknown").status_code == 403


def test_repository_keeps_full_reports_for_controlled_moderation_access() -> None:
    _client_instance, repository = _client("moderation")
    report, created = repository.record_safety_report(SafetyReport(
        report_id="report-1",
        table_id="moderation",
        reporter_id="alice",
        target_participant_id="bob",
        category="privacy",
        description="不应公开个人信息",
        state_version=0,
    ))

    assert created is True
    assert repository.safety_reports("moderation") == [report]
    assert repository.safety_reports("moderation", "bob") == []


def test_json_repository_persists_reports_and_accepts_legacy_tables(tmp_path) -> None:
    path = tmp_path / "reports.json"
    repository = JsonTableRepository(path)
    repository.create("persisted", "Q", [_seed("alice"), _seed("bob")])
    report, _created = repository.record_safety_report(SafetyReport(
        report_id="report-1",
        table_id="persisted",
        reporter_id="alice",
        target_participant_id="bob",
        category="spam",
        description="重复推广内容",
        state_version=0,
    ))

    restored = JsonTableRepository(path)
    assert restored.safety_reports("persisted", "alice") == [report]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tables"]["persisted"].pop("safety_reports")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    legacy = JsonTableRepository(path)
    assert legacy.safety_reports("persisted") == []
