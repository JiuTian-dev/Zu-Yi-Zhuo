import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed


def _seed(participant_id: str, role: str = "实践者") -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=f"{participant_id} 展示名",
        role=role,
        declared_position=f"{participant_id} 私有立场",
        relevant_experience=[{
            "text": f"{participant_id} 私有经历",
            "source_ref": f"private:{participant_id}",
        }],
    )


def _create_invitation(
    repository: InMemoryTableRepository,
    table_id: str,
    candidate_id: str = "candidate",
    *,
    member_count: int = 1,
) -> str:
    members = [_seed(f"{table_id}-member-{index}") for index in range(member_count)]
    repository.create(table_id, f"{table_id} 的问题", members)
    invitation = repository.create_invitation(
        table_id,
        members[0].participant_id,
        _seed(candidate_id, "研究者"),
        f"{table_id} 需要你的视角",
    )
    return invitation.invitation_id


def _header_identity(request) -> str | None:
    return request.headers.get("x-user-id")


def test_invitation_inbox_is_self_scoped_redacted_and_stably_sorted() -> None:
    repository = InMemoryTableRepository()
    _create_invitation(repository, "b-table")
    _create_invitation(repository, "a-table")
    _create_invitation(repository, "other-table", "other")
    client = TestClient(create_app(repository, identity_resolver=_header_identity))

    missing = client.get(
        "/participants/candidate/invitations?viewer_id=candidate"
    )
    wrong_identity = client.get(
        "/participants/candidate/invitations?viewer_id=candidate",
        headers={"X-User-ID": "other"},
    )
    wrong_viewer = client.get(
        "/participants/candidate/invitations?viewer_id=other",
        headers={"X-User-ID": "other"},
    )
    response = client.get(
        "/participants/candidate/invitations?viewer_id=candidate",
        headers={"X-User-ID": "candidate"},
    )

    assert missing.status_code == 401
    assert wrong_identity.status_code == 403
    assert wrong_viewer.status_code == 403
    assert response.status_code == 200
    payload = response.json()
    assert payload["participant_id"] == "candidate"
    assert payload["total"] == 2
    assert payload["offset"] == 0
    assert payload["limit"] == 30
    assert [item["invitation"]["table_id"] for item in payload["items"]] == [
        "a-table",
        "b-table",
    ]
    assert all(item["can_respond"] is True for item in payload["items"])
    assert all(item["unavailable_reason"] is None for item in payload["items"])
    assert payload["items"][0]["table"]["core_question"] == "a-table 的问题"
    assert "私有立场" not in response.text
    assert "私有经历" not in response.text
    assert "private:" not in response.text
    assert "other-table" not in response.text


def test_invitation_inbox_filters_and_paginates_after_status_sorting() -> None:
    repository = InMemoryTableRepository()
    pending_id = _create_invitation(repository, "z-pending")
    accepted_id = _create_invitation(repository, "a-accepted")
    declined_id = _create_invitation(repository, "m-declined")
    repository.respond_invitation("a-accepted", accepted_id, "candidate", True)
    repository.respond_invitation("m-declined", declined_id, "candidate", False)
    client = TestClient(create_app(repository))

    page = client.get(
        "/participants/candidate/invitations"
        "?viewer_id=candidate&offset=1&limit=1"
    )
    declined = client.get(
        "/participants/candidate/invitations"
        "?viewer_id=candidate&status=declined"
    )

    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert page.json()["offset"] == 1
    assert page.json()["limit"] == 1
    assert page.json()["items"][0]["invitation"]["invitation_id"] == accepted_id
    assert page.json()["items"][0]["unavailable_reason"] == "invitation_processed"
    assert declined.status_code == 200
    assert declined.json()["total"] == 1
    assert declined.json()["items"][0]["invitation"]["invitation_id"] == declined_id
    assert client.get(
        "/participants/candidate/invitations?viewer_id=candidate&status=unknown"
    ).status_code == 422
    assert pending_id != accepted_id


def test_candidate_can_accept_directly_from_inbox_identifiers() -> None:
    repository = InMemoryTableRepository()
    invitation_id = _create_invitation(repository, "journey")
    client = TestClient(create_app(repository))
    inbox = client.get(
        "/participants/candidate/invitations?viewer_id=candidate&status=pending"
    ).json()
    item = inbox["items"][0]

    accepted = client.post(
        f"/tables/{item['invitation']['table_id']}/invitations/"
        f"{invitation_id}/respond?participant_id=candidate",
        json={"accept": True},
    )
    refreshed = client.get(
        "/participants/candidate/invitations?viewer_id=candidate&status=accepted"
    )

    assert accepted.status_code == 200
    assert "candidate" in accepted.json()["state"]["participants"]
    assert refreshed.status_code == 200
    assert refreshed.json()["total"] == 1
    assert refreshed.json()["items"][0]["can_respond"] is False
    assert refreshed.json()["items"][0]["unavailable_reason"] == "invitation_processed"


def test_invitation_inbox_explains_why_pending_items_are_not_actionable() -> None:
    repository = InMemoryTableRepository()
    _create_invitation(repository, "closed")
    repository.close_table("closed")

    _create_invitation(repository, "expired")
    repository.soft_expire_table("expired", "组合价值下降")

    _create_invitation(repository, "full", member_count=4)
    repository.add_participant("full", _seed("full-last-seat"))

    _create_invitation(repository, "blocked")
    repository.set_no_match("blocked-member-0", "candidate")

    _create_invitation(repository, "open")
    client = TestClient(create_app(repository))
    response = client.get(
        "/participants/candidate/invitations?viewer_id=candidate&status=pending"
    )

    assert response.status_code == 200
    items = {
        item["invitation"]["table_id"]: item
        for item in response.json()["items"]
    }
    assert items["closed"]["unavailable_reason"] == "table_closed"
    assert items["expired"]["unavailable_reason"] == "table_soft_expired"
    assert items["full"]["unavailable_reason"] == "table_full"
    assert items["blocked"]["unavailable_reason"] == "matching_disabled"
    assert items["open"]["unavailable_reason"] is None
    assert items["open"]["can_respond"] is True
    assert all(
        item["can_respond"] is False
        for table_id, item in items.items()
        if table_id != "open"
    )


def test_invitation_inbox_recovers_from_existing_json_invitation_ledger(tmp_path) -> None:
    path = tmp_path / "inbox.json"
    repository = JsonTableRepository(path)
    invitation_id = _create_invitation(repository, "persisted")

    restored = JsonTableRepository(path)
    response = TestClient(create_app(restored)).get(
        "/participants/candidate/invitations?viewer_id=candidate"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["invitation"]["invitation_id"] == invitation_id
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["tables"]["persisted"]["invitations"][0]["candidate"][
        "declared_position"
    ] == "candidate 私有立场"
    assert "私有立场" not in response.text
