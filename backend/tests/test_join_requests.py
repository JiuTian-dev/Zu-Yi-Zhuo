import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed


def seed(participant_id: str, *, preference: str = "few", display_name: str | None = None) -> dict:
    return {
        "participant_id": participant_id,
        "display_name": display_name or participant_id,
        "role": "实践者",
        "declared_position": f"{participant_id} 的私有立场",
        "relevant_experience": [
            {"text": f"{participant_id} 的私有经历", "source_ref": f"private:{participant_id}"}
        ],
        "roundtable_invite_preference": preference,
        "public_signal_ids": [f"signal:{participant_id}"],
    }


def setup_client(repository: InMemoryTableRepository | JsonTableRepository):
    client = TestClient(create_app(repository))
    repository.create("join", "如何把想法变成行动？", [
        ParticipantSeed.model_validate(seed("member")),
    ])
    return client


def test_candidate_request_is_redacted_and_approval_only_creates_invitation() -> None:
    repository = InMemoryTableRepository()
    client = setup_client(repository)
    candidate = seed("candidate", display_name="候选人")

    created = client.post(
        "/tables/join/join-requests?participant_id=candidate",
        json={"request_id": "jr-1", "candidate": candidate, "message": "希望补充现场经验"},
    )
    assert created.status_code == 201
    assert created.json() == {
        "request_id": "jr-1",
        "table_id": "join",
        "participant_id": "candidate",
        "display_name": "候选人",
        "role": "实践者",
        "message": "希望补充现场经验",
        "status": "pending",
        "invitation_id": None,
    }
    assert "私有经历" not in created.text and "declared_position" not in created.text

    assert client.get("/tables/join/join-requests?participant_id=candidate").json() == [created.json()]
    member_view = client.get("/tables/join/join-requests?participant_id=member")
    assert member_view.status_code == 200 and member_view.json() == [created.json()]
    outsider_view = client.get("/tables/join/join-requests?participant_id=outsider")
    assert outsider_view.status_code == 200 and outsider_view.json() == []

    approved = client.post(
        "/tables/join/join-requests/jr-1/approve?participant_id=member",
        json={"reason": "补充现场经验"},
    )
    assert approved.status_code == 200
    assert approved.json()["request"]["status"] == "invited"
    invitation = approved.json()["invitation"]
    assert invitation["participant_id"] == "candidate"
    assert "私有经历" not in approved.text
    assert list(repository.get("join").participants) == ["member"]

    # Replaying the approval is idempotent and does not create a second invitation.
    replay = client.post(
        "/tables/join/join-requests/jr-1/approve?participant_id=member",
        json={"reason": "不同文案也不会重复发邀请"},
    )
    assert replay.status_code == 200
    assert replay.json()["invitation"]["invitation_id"] == invitation["invitation_id"]
    assert len(repository.invitations("join")) == 1

    accepted = client.post(
        f"/tables/join/invitations/{invitation['invitation_id']}/respond?participant_id=candidate",
        json={"accept": True},
    )
    assert accepted.status_code == 200
    assert set(repository.get("join").participants) == {"member", "candidate"}


def test_join_request_decline_is_idempotent_and_blocks_retries() -> None:
    repository = InMemoryTableRepository()
    client = setup_client(repository)
    candidate = seed("candidate")
    assert client.post(
        "/tables/join/join-requests?participant_id=candidate",
        json={"request_id": "jr-1", "candidate": candidate},
    ).status_code == 201

    declined = client.post(
        "/tables/join/join-requests/jr-1/decline?participant_id=member"
    )
    assert declined.status_code == 200 and declined.json()["status"] == "declined"
    assert client.post(
        "/tables/join/join-requests/jr-1/decline?participant_id=member"
    ).json()["status"] == "declined"
    assert client.post(
        "/tables/join/join-requests/jr-1/approve?participant_id=member",
        json={"reason": "不应重新邀请"},
    ).status_code == 409
    assert client.post(
        "/tables/join/join-requests?participant_id=candidate",
        json={"request_id": "jr-2", "candidate": candidate},
    ).status_code == 409


def test_join_request_enforces_identity_and_matching_constraints() -> None:
    repository = InMemoryTableRepository()
    client = setup_client(repository)
    candidate = seed("candidate")
    mismatch = client.post(
        "/tables/join/join-requests?participant_id=someone-else",
        json={"request_id": "jr-1", "candidate": candidate},
    )
    assert mismatch.status_code == 403
    self_initiated = client.post(
        "/tables/join/join-requests?participant_id=candidate",
        json={"request_id": "jr-1", "candidate": {**candidate, "roundtable_invite_preference": "none"}},
    )
    assert self_initiated.status_code == 201
    assert self_initiated.json()["status"] == "pending"

    # A member's no-match preference is a hard boundary for candidate-initiated matching.
    repository.set_no_match("member", "blocked")
    blocked = seed("blocked")
    assert client.post(
        "/tables/join/join-requests?participant_id=blocked",
        json={"request_id": "jr-blocked", "candidate": blocked},
    ).status_code == 409
    assert client.post(
        "/tables/join/join-requests/jr-1/approve?participant_id=outsider",
        json={"reason": "越权"},
    ).status_code == 403


def test_json_repository_persists_join_request_and_invitation_across_restart(tmp_path) -> None:
    path = tmp_path / "join-requests.json"
    repository = JsonTableRepository(path)
    client = setup_client(repository)
    candidate = seed("candidate")
    assert client.post(
        "/tables/join/join-requests?participant_id=candidate",
        json={"request_id": "jr-1", "candidate": candidate, "message": "异步加入"},
    ).status_code == 201
    approved = client.post(
        "/tables/join/join-requests/jr-1/approve?participant_id=member",
        json={"reason": "补充视角"},
    ).json()

    restored = JsonTableRepository(path)
    restored_client = TestClient(create_app(restored))
    requests = restored_client.get("/tables/join/join-requests?participant_id=member")
    assert requests.status_code == 200
    assert requests.json()[0]["status"] == "invited"
    invitations = restored_client.get("/tables/join/invitations?participant_id=candidate")
    assert invitations.status_code == 200
    assert invitations.json()[0]["invitation_id"] == approved["invitation"]["invitation_id"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["tables"]["join"]["join_requests"][0]["candidate"]["declared_position"].startswith("candidate")


def test_join_request_rejects_full_tables() -> None:
    repository = InMemoryTableRepository()
    participants = [
        ParticipantSeed.model_validate(seed(f"p{index}"))
        for index in range(5)
    ]
    repository.create("full", "Q", participants)
    client = TestClient(create_app(repository))
    response = client.post(
        "/tables/full/join-requests?participant_id=candidate",
        json={"request_id": "jr-full", "candidate": seed("candidate")},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "table cannot exceed 5 participants"}
