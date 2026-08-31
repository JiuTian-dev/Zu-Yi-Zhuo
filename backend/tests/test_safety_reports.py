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


def _moderator(request) -> str | None:
    return request.headers.get("x-moderator-id")


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


def test_moderation_report_queue_requires_trusted_identity_and_returns_full_queue() -> None:
    repository = InMemoryTableRepository()
    repository.create("moderation-api", "Q", [_seed("alice"), _seed("bob")])
    report, _created = repository.record_safety_report(SafetyReport(
        report_id="report-1",
        table_id="moderation-api",
        reporter_id="alice",
        target_participant_id="bob",
        category="privacy",
        description="不应公开个人信息",
        state_version=0,
    ))
    client = TestClient(create_app(repository, moderator_resolver=_moderator))

    assert client.get("/tables/moderation-api/safety-reports/moderation").status_code == 401
    queue = client.get(
        "/tables/moderation-api/safety-reports/moderation",
        headers={"X-Moderator-ID": "mod-1"},
    )
    assert queue.status_code == 200
    assert queue.json() == [report.model_dump(mode="json")]
    assert client.get(
        "/tables/moderation-api/safety-reports?reporter_id=bob"
    ).status_code == 200
    assert client.get(
        "/tables/moderation-api/safety-reports?reporter_id=bob"
    ).json() == []


def test_moderation_report_queue_is_unavailable_without_moderator_configuration() -> None:
    client, _repository = _client("no-moderator")
    response = client.get("/tables/no-moderator/safety-reports/moderation")
    assert response.status_code == 503


def test_moderator_can_advance_report_status_without_peer_visibility() -> None:
    repository = InMemoryTableRepository()
    repository.create("status-api", "Q", [_seed("alice"), _seed("bob")])
    repository.record_safety_report(SafetyReport(
        report_id="report-1",
        table_id="status-api",
        reporter_id="alice",
        target_participant_id="bob",
        category="harassment",
        description="需要审核的私密描述",
        state_version=0,
    ))
    client = TestClient(create_app(repository, moderator_resolver=_moderator))
    path = "/tables/status-api/safety-reports/report-1"

    assert client.patch(path, json={"status": "acknowledged"}).status_code == 401
    acknowledged = client.patch(
        path,
        json={"status": "acknowledged"},
        headers={"X-Moderator-ID": "mod-1"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    assert client.patch(
        path,
        json={"status": "acknowledged"},
        headers={"X-Moderator-ID": "mod-1"},
    ).json() == acknowledged.json()
    resolved = client.patch(
        path,
        json={"status": "resolved"},
        headers={"X-Moderator-ID": "mod-1"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert client.patch(
        path,
        json={"status": "acknowledged"},
        headers={"X-Moderator-ID": "mod-1"},
    ).status_code == 409
    assert client.get("/tables/status-api/safety-reports?reporter_id=alice").json()[0]["status"] == "resolved"


def test_status_transitions_keep_trusted_identity_reason_and_private_history() -> None:
    repository = InMemoryTableRepository()
    repository.create("audit-api", "Q", [_seed("alice"), _seed("bob")])
    repository.record_safety_report(SafetyReport(
        report_id="report-1",
        table_id="audit-api",
        reporter_id="alice",
        target_participant_id="bob",
        category="privacy",
        description="需要审核的私密描述",
        state_version=0,
    ))
    client = TestClient(create_app(repository, moderator_resolver=_moderator))
    path = "/tables/audit-api/safety-reports/report-1"

    first = client.patch(
        path,
        json={"status": "acknowledged", "reason": "已确认进入审核队列"},
        headers={"X-Moderator-ID": "mod-7"},
    )
    assert first.status_code == 200
    assert client.patch(
        path,
        json={"status": "acknowledged", "reason": "重复提交不应产生事件"},
        headers={"X-Moderator-ID": "mod-8"},
    ).status_code == 200
    second = client.patch(
        path,
        json={"status": "resolved"},
        headers={"X-Moderator-ID": "mod-8"},
    )
    assert second.status_code == 200

    history = client.get(
        "/tables/audit-api/safety-reports/report-1/history",
        headers={"X-Moderator-ID": "mod-9"},
    )
    assert history.status_code == 200
    assert history.json() == [
        {
            "event_id": "audit-api:report-1:acknowledged",
            "table_id": "audit-api",
            "report_id": "report-1",
            "moderator_id": "mod-7",
            "from_status": "open",
            "to_status": "acknowledged",
            "reason": "已确认进入审核队列",
        },
        {
            "event_id": "audit-api:report-1:resolved",
            "table_id": "audit-api",
            "report_id": "report-1",
            "moderator_id": "mod-8",
            "from_status": "acknowledged",
            "to_status": "resolved",
            "reason": None,
        },
    ]


def test_status_history_requires_moderator_and_known_report() -> None:
    client, _repository = _client("audit-guards")
    assert client.get(
        "/tables/audit-guards/safety-reports/report-1/history"
    ).status_code == 503
    repository = InMemoryTableRepository()
    repository.create("audit-guards", "Q", [_seed("alice"), _seed("bob")])
    trusted = TestClient(create_app(repository, moderator_resolver=_moderator))
    assert trusted.get(
        "/tables/audit-guards/safety-reports/unknown/history",
        headers={"X-Moderator-ID": "mod-1"},
    ).status_code == 404


def test_json_report_status_transition_survives_restart(tmp_path) -> None:
    path = tmp_path / "status.json"
    repository = JsonTableRepository(path)
    repository.create("status-json", "Q", [_seed("alice"), _seed("bob")])
    repository.record_safety_report(SafetyReport(
        report_id="report-1",
        table_id="status-json",
        reporter_id="alice",
        target_participant_id="bob",
        category="spam",
        description="审核状态需要恢复",
        state_version=0,
    ))
    repository.update_safety_report_status(
        "status-json", "report-1", "acknowledged", moderator_id="mod-1", reason="先确认事实",
    )

    restored = JsonTableRepository(path)
    assert restored.safety_reports("status-json")[0].status == "acknowledged"
    assert restored.safety_report_audits("status-json")[0].moderator_id == "mod-1"
    restored.update_safety_report_status("status-json", "report-1", "resolved", moderator_id="mod-2")
    persisted = JsonTableRepository(path)
    assert persisted.safety_reports("status-json")[0].status == "resolved"
    assert [item.to_status for item in persisted.safety_report_audits("status-json")] == [
        "acknowledged", "resolved"
    ]


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
