import asyncio

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository


class _Source:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = []

    async def search(self, *, query, limit):
        self.calls.append((query, limit))
        return self.candidates[:limit]


class _HangingSource:
    async def search(self, *, query, limit):
        await asyncio.sleep(0.2)
        return []


def _candidate(participant_id: str, role: str) -> dict:
    return {
        "participant_id": participant_id,
        "display_name": participant_id,
        "role": role,
        "declared_position": "公开立场",
        "relevant_experience": [{"text": "公开经历", "source_ref": "authorized:answer"}],
    }


def _table(client: TestClient, table_id: str = "candidate-table") -> None:
    response = client.post("/tables", json={
        "table_id": table_id,
        "core_question": "AI 采购如何真正落地？",
        "participants": [
            _candidate("p1", "产品负责人"),
            _candidate("p2", "研究员"),
        ],
    })
    assert response.status_code == 201


def test_candidate_preview_returns_gap_aware_recommendations_without_mutation() -> None:
    source = _Source([_candidate("p3", "实践者"), _candidate("p4", "产品经理")])
    client = TestClient(create_app(candidate_source=source))
    _table(client)

    response = client.post(
        "/tables/candidate-table/candidate-preview?participant_id=p1",
        json={"limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["table_id"] == "candidate-table"
    assert payload["open_seats"] == 3
    assert "实践者" in payload["role_gaps"]
    assert [item["participant_id"] for item in payload["candidates"]] == ["p3", "p4"]
    assert payload["candidates"][0]["reason"]
    assert source.calls == [("AI 采购如何真正落地？", 2)]
    assert client.get("/tables/candidate-table").json()["version"] == 0
    assert client.get("/tables/candidate-table/invitations?participant_id=p1").json() == []


def test_candidate_preview_filters_members_and_previously_invited_candidates() -> None:
    source = _Source([
        _candidate("p1", "产品负责人"),
        _candidate("p2", "研究员"),
        _candidate("p3", "实践者"),
    ])
    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository, candidate_source=source))
    _table(client, "filter-table")
    invited = client.post(
        "/tables/filter-table/invitations?inviter_id=p1",
        json={"candidate": _candidate("p3", "实践者"), "reason": "补充落地视角"},
    )
    assert invited.status_code == 201

    response = client.post(
        "/tables/filter-table/candidate-preview?participant_id=p1",
        json={"limit": 10},
    )

    assert response.status_code == 200
    assert [item["participant_id"] for item in response.json()["candidates"]] == []
    assert repository.get("filter-table").version == 0


def test_candidate_preview_requires_member_and_open_active_table() -> None:
    source = _Source([_candidate("p3", "实践者")])
    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository, candidate_source=source))
    _table(client, "guard-table")

    assert client.post(
        "/tables/guard-table/candidate-preview?participant_id=ghost", json={}
    ).status_code == 403
    repository.close_table("guard-table")
    assert client.post(
        "/tables/guard-table/candidate-preview?participant_id=p1", json={}
    ).status_code == 409

    expired_repository = InMemoryTableRepository()
    expired = TestClient(create_app(expired_repository, candidate_source=source))
    _table(expired, "expired-table")
    expired_repository.soft_expire_table("expired-table", "问题热度下降")
    assert expired.post(
        "/tables/expired-table/candidate-preview?participant_id=p1", json={}
    ).status_code == 409


def test_candidate_preview_rejects_full_tables_and_missing_sources() -> None:
    full_client = TestClient(create_app(candidate_source=_Source([])))
    response = full_client.post("/tables", json={
        "table_id": "full-table",
        "core_question": "Q",
        "participants": [_candidate(f"p{i}", "产品") for i in range(5)],
    })
    assert response.status_code == 201
    assert full_client.post(
        "/tables/full-table/candidate-preview?participant_id=p0", json={}
    ).status_code == 409

    missing_client = TestClient(create_app())
    _table(missing_client, "missing-source-table")
    response = missing_client.post(
        "/tables/missing-source-table/candidate-preview?participant_id=p1", json={}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "candidate source is not configured"}


def test_candidate_preview_fails_closed_on_invalid_source_and_timeout() -> None:
    invalid = _Source([{"participant_id": "p3"}])
    client = TestClient(create_app(candidate_source=invalid))
    _table(client, "invalid-source-table")
    assert client.post(
        "/tables/invalid-source-table/candidate-preview?participant_id=p1", json={}
    ).status_code == 502

    timeout_client = TestClient(create_app(
        candidate_source=_HangingSource(), candidate_source_timeout_seconds=0.01,
    ))
    _table(timeout_client, "timeout-source-table")
    response = timeout_client.post(
        "/tables/timeout-source-table/candidate-preview?participant_id=p1", json={}
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "candidate source timed out"}
