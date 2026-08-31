from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import HumanTurn, ParticipantSeed


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def _resolver(request) -> str | None:
    return request.headers.get("x-user-id")


def _client() -> tuple[TestClient, InMemoryTableRepository]:
    repository = InMemoryTableRepository()
    repository.create("privileged", "如何把讨论推进下去？", [_seed("p1")])
    return TestClient(create_app(repository, identity_resolver=_resolver)), repository


def test_production_identity_is_required_for_direct_seat_addition_and_close() -> None:
    client, repository = _client()
    participant = _seed("p2").model_dump(mode="json")

    assert client.post("/tables/privileged/participants", json=participant).status_code == 401
    assert client.post(
        "/tables/privileged/participants?inviter_id=p1",
        json=participant,
        headers={"X-User-ID": "p2"},
    ).status_code == 403
    assert client.post(
        "/tables/privileged/participants?inviter_id=p1",
        json=participant,
        headers={"X-User-ID": "p1"},
    ).status_code == 200

    repository.append_turn(
        "privileged",
        HumanTurn(turn_id=1, participant_id="p1", text="我会先验证一个小范围方案。"),
    )
    assert client.post(
        "/tables/privileged/close?participant_id=p1",
        headers={"X-User-ID": "p2"},
    ).status_code == 403
    closed = client.post(
        "/tables/privileged/close?participant_id=p1",
        headers={"X-User-ID": "p1"},
    )
    assert closed.status_code == 200
    assert repository.get("privileged").conversation.closed is True


def test_production_identity_guards_recompose_and_intervention_audit_reads() -> None:
    client, repository = _client()
    repository.add_participant("privileged", _seed("p2"))
    repository.append_turn(
        "privileged",
        HumanTurn(turn_id=1, participant_id="p1", text="我会先验证一个小范围方案。"),
    )
    assert client.post(
        "/tables/privileged/close?participant_id=p1",
        headers={"X-User-ID": "p1"},
    ).status_code == 200

    payload = {
        "table_id": "next-privileged",
        "participants": [_seed("p1").model_dump(mode="json"), _seed("p2").model_dump(mode="json")],
    }
    assert client.post(
        "/tables/privileged/recompose", json=payload,
    ).status_code == 401
    assert client.post(
        "/tables/privileged/recompose?participant_id=p1",
        json=payload,
        headers={"X-User-ID": "p2"},
    ).status_code == 403
    recomposed = client.post(
        "/tables/privileged/recompose?participant_id=p1",
        json=payload,
        headers={"X-User-ID": "p1"},
    )
    assert recomposed.status_code == 201
    assert recomposed.json()["source_table_id"] == "privileged"

    assert client.get("/tables/privileged/interventions").status_code == 401
    assert client.get(
        "/tables/privileged/interventions?participant_id=missing",
        headers={"X-User-ID": "missing"},
    ).status_code == 403
    assert client.get(
        "/tables/privileged/interventions?participant_id=p1",
        headers={"X-User-ID": "p1"},
    ).status_code == 200
