import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.intent_sessions import (
    ActiveIntentSessionStore,
    IntentSessionCapacityExhausted,
    IntentSessionTurnLimitReached,
    IntentSessionUnavailable,
)
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


def _seed(participant_id: str, role: str = "实践者") -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="公开立场",
    )


class _CandidateSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, *, query: str, limit: int):
        self.calls.append((query, limit))
        return [
            {
                "participant_id": "source-1",
                "display_name": "source-1",
                "role": "实践者",
                "declared_position": "私有立场",
                "relevant_experience": [{"text": "私有经历", "source_ref": "auth"}],
                "public_signal_ids": ["source-signal-1"],
            },
            {
                "participant_id": "source-2",
                "display_name": "source-2",
                "role": "专业者",
                "declared_position": "私有立场",
                "relevant_experience": [{"text": "私有经历", "source_ref": "auth"}],
                "public_signal_ids": ["source-signal-2"],
            },
        ][:limit]


def test_multi_turn_intent_session_clarifies_then_routes_existing_table_without_writing() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "hiking-table",
        "城市徒步路线和装备怎么选？",
        [_seed("member-1")],
    )
    client = TestClient(create_app(repository))

    started = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "找人聊"},
    )

    assert started.status_code == 201
    first = started.json()
    session_id = first["session_id"]
    assert first["status"] == "clarifying"
    assert first["turn_count"] == 1
    assert first["remaining_turns"] == 5
    assert first["messages"] == ["找人聊"]
    assert first["preview"]["route"] == "clarify"

    continued = client.post(
        f"/participants/visitor/intent-sessions/{session_id}/turns?viewer_id=visitor",
        json={"message": "我想聊城市徒步路线和装备选择"},
    )

    assert continued.status_code == 200
    second = continued.json()
    assert second["status"] == "ready"
    assert second["turn_count"] == 2
    assert second["remaining_turns"] == 4
    assert second["messages"] == ["找人聊", "我想聊城市徒步路线和装备选择"]
    assert second["preview"]["route"] == "join_existing"
    assert second["preview"]["candidates"][0]["table_id"] == "hiking-table"
    assert [state.table_id for state in repository.list_tables()] == ["hiking-table"]

    reread = client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
    )
    assert reread.status_code == 200
    assert reread.json()["preview"]["route"] == "join_existing"

    deleted = client.delete(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
    )
    assert deleted.status_code == 204
    assert client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
    ).status_code == 404


def test_intent_session_supports_explicit_context_replacement() -> None:
    repository = InMemoryTableRepository()
    repository.create("agent-table", "企业 Agent 的采购预算如何落地？", [_seed("m1")])
    repository.create("hiking-table", "城市徒步路线和装备怎么选？", [_seed("m2")])
    client = TestClient(create_app(repository))

    started = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "我想聊企业 Agent 的采购预算"},
    )
    session_id = started.json()["session_id"]
    assert started.json()["preview"]["candidates"][0]["table_id"] == "agent-table"

    corrected = client.post(
        f"/participants/visitor/intent-sessions/{session_id}/turns?viewer_id=visitor",
        json={
            "message": "改成城市徒步路线和装备",
            "replace_context": True,
        },
    )

    assert corrected.status_code == 200
    payload = corrected.json()
    assert payload["messages"] == ["改成城市徒步路线和装备"]
    assert payload["turn_count"] == 2
    assert payload["preview"]["route"] == "join_existing"
    assert [item["table_id"] for item in payload["preview"]["candidates"]] == ["hiking-table"]


def test_new_table_intent_hands_off_to_authorized_candidate_preview_and_ticket() -> None:
    source = _CandidateSource()
    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository, candidate_source=source))

    started = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "我想找人聊城市徒步路线和装备选择"},
    )
    assert started.status_code == 201
    assert started.json()["preview"]["route"] == "new_table"
    session_id = started.json()["session_id"]

    preview = client.post(
        f"/participants/visitor/intent-sessions/{session_id}/source-preview?viewer_id=visitor",
        json={"table_size": 2, "limit": 2},
    )

    assert preview.status_code == 200
    plan = preview.json()
    token = plan["preview_token"]
    assert token
    assert plan["core_question"] == "城市徒步路线和装备选择"
    assert {seat["participant_id"] for seat in plan["selected"]} == {"source-1", "source-2"}
    assert "私有立场" not in preview.text
    assert "私有经历" not in preview.text
    assert source.calls == [("城市徒步路线和装备选择", 2)]
    assert repository.list_tables() == []

    confirmed = client.post(
        "/matches/source-confirm",
        json={"preview_token": token, "table_id": "intent-source-table"},
    )
    assert confirmed.status_code == 201
    assert confirmed.json()["state"]["table_id"] == "intent-source-table"
    assert set(confirmed.json()["state"]["origin_signal_ids"]) == {
        "source-signal-1",
        "source-signal-2",
    }
    assert source.calls == [("城市徒步路线和装备选择", 2)]


def test_intent_source_preview_requires_ready_new_table_route() -> None:
    client = TestClient(create_app())
    clarify = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "找人聊"},
    )
    clarify_response = client.post(
        f"/participants/visitor/intent-sessions/{clarify.json()['session_id']}/source-preview?viewer_id=visitor",
        json={},
    )
    assert clarify_response.status_code == 409
    assert clarify_response.json()["detail"] == "active intent session still needs clarification"

    repository = InMemoryTableRepository()
    repository.create("existing", "城市徒步路线和装备", [_seed("m1")])
    existing_client = TestClient(create_app(repository))
    existing = existing_client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "城市徒步路线和装备"},
    )
    existing_response = existing_client.post(
        f"/participants/visitor/intent-sessions/{existing.json()['session_id']}/source-preview?viewer_id=visitor",
        json={},
    )
    assert existing_response.status_code == 409
    assert existing_response.json()["detail"] == "active intent session already has existing table candidates"


def test_intent_source_preview_is_unavailable_without_candidate_source() -> None:
    client = TestClient(create_app())
    started = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "城市徒步路线和装备选择"},
    )
    response = client.post(
        f"/participants/visitor/intent-sessions/{started.json()['session_id']}/source-preview?viewer_id=visitor",
        json={},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "candidate source is not configured"}


def test_intent_session_is_bounded_and_reports_exhaustion() -> None:
    client = TestClient(create_app())
    started = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "找人聊"},
    )
    session_id = started.json()["session_id"]

    for turn in range(2, 7):
        response = client.post(
            f"/participants/visitor/intent-sessions/{session_id}/turns?viewer_id=visitor",
            json={"message": "找人聊"},
        )
        assert response.status_code == 200

    exhausted = response.json()
    assert exhausted["status"] == "exhausted"
    assert exhausted["turn_count"] == 6
    assert exhausted["remaining_turns"] == 0
    assert exhausted["preview"]["route"] == "clarify"

    blocked = client.post(
        f"/participants/visitor/intent-sessions/{session_id}/turns?viewer_id=visitor",
        json={"message": "再说一轮"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "active intent session turn limit reached"


def test_intent_session_identity_is_self_scoped_and_resolver_backed() -> None:
    def resolver(request) -> str | None:
        return request.headers.get("x-user-id")

    client = TestClient(create_app(identity_resolver=resolver))
    path = "/participants/visitor/intent-sessions?viewer_id=visitor"

    assert client.post(path, json={"message": "找人聊"}).status_code == 401
    assert client.post(
        path,
        headers={"X-User-ID": "other"},
        json={"message": "找人聊"},
    ).status_code == 403
    started = client.post(
        path,
        headers={"X-User-ID": "visitor"},
        json={"message": "找人聊"},
    )
    assert started.status_code == 201
    session_id = started.json()["session_id"]

    assert client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
        headers={"X-User-ID": "other"},
    ).status_code == 403
    assert client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
        headers={"X-User-ID": "visitor"},
    ).status_code == 200


def test_intent_session_expiry_is_absolute_for_reads_and_turns_refresh_ttl() -> None:
    now = [100.0]
    client = TestClient(create_app(clock=lambda: now[0], intent_session_ttl_seconds=5))
    started = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "找人聊"},
    )
    session_id = started.json()["session_id"]

    now[0] = 104.0
    assert client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
    ).status_code == 200
    now[0] = 105.1
    assert client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
    ).status_code == 404

    started = client.post(
        "/participants/visitor/intent-sessions?viewer_id=visitor",
        json={"message": "找人聊"},
    )
    session_id = started.json()["session_id"]
    now[0] = 109.0
    assert client.post(
        f"/participants/visitor/intent-sessions/{session_id}/turns?viewer_id=visitor",
        json={"message": "旅行路线"},
    ).status_code == 200
    now[0] = 113.9
    assert client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
    ).status_code == 200
    now[0] = 114.1
    assert client.get(
        f"/participants/visitor/intent-sessions/{session_id}?viewer_id=visitor",
    ).status_code == 404


def test_intent_session_store_enforces_owner_capacity_and_turn_limit() -> None:
    now = [0.0]
    store = ActiveIntentSessionStore(
        ttl_seconds=5,
        max_sessions=1,
        max_turns=2,
        clock=lambda: now[0],
    )
    session = store.create(participant_id="p1", message="找人聊", limit=5)
    with pytest.raises(IntentSessionCapacityExhausted):
        store.create(participant_id="p2", message="找人聊", limit=5)
    with pytest.raises(IntentSessionUnavailable):
        store.get(session.session_id, "p2")
    store.append(session.session_id, "p1", "旅行")
    with pytest.raises(IntentSessionTurnLimitReached):
        store.append(session.session_id, "p1", "再问一轮")
    now[0] = 5.0
    store.create(participant_id="p2", message="找人聊", limit=5)
