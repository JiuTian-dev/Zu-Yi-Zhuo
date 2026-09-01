import json

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import InvitationPreference, ParticipantSeed


def _seed(participant_id: str, role: str = "实践者") -> dict:
    return {
        "participant_id": participant_id,
        "display_name": participant_id,
        "role": role,
        "declared_position": f"{participant_id} 的公开立场",
        "roundtable_invite_preference": "few",
    }


class _Source:
    def __init__(self, candidates: list[dict]) -> None:
        self.candidates = candidates

    async def search(self, *, query: str, limit: int):
        return self.candidates[:limit]


def test_account_preference_is_self_scoped_and_defaults_to_few() -> None:
    client = TestClient(create_app())

    default = client.get(
        "/participants/candidate/invitation-preference?viewer_id=candidate"
    )
    forbidden = client.get(
        "/participants/candidate/invitation-preference?viewer_id=other"
    )
    saved = client.put(
        "/participants/candidate/invitation-preference?viewer_id=candidate",
        json={"preference": "none"},
    )
    current = client.get(
        "/participants/candidate/invitation-preference?viewer_id=candidate"
    )

    assert default.json() == {"participant_id": "candidate", "preference": "few"}
    assert forbidden.status_code == 403
    assert saved.json() == {"participant_id": "candidate", "preference": "none"}
    assert current.json() == saved.json()


def test_account_opt_out_overrides_stale_match_and_source_candidates() -> None:
    repository = InMemoryTableRepository()
    repository.set_account_invitation_preference("opted-out", InvitationPreference.NONE)
    source = _Source([
        _seed("opted-out", "架构师"),
        _seed("eligible-1", "产品经理"),
        _seed("eligible-2", "研究员"),
    ])
    client = TestClient(create_app(repository, candidate_source=source))
    payload = {
        "core_question": "AI 产品如何落地？",
        "table_size": 2,
        "candidates": source.candidates,
    }

    preview = client.post("/matches/preview", json=payload)
    confirmed = client.post(
        "/matches/confirm",
        json={**payload, "table_id": "preference-match"},
    )
    source_preview = client.post(
        "/matches/source-preview",
        json={"core_question": payload["core_question"], "table_size": 2, "limit": 3},
    )
    repository.create(
        "open-table",
        payload["core_question"],
        [ParticipantSeed.model_validate(_seed("member"))],
    )
    candidate_preview = client.post(
        "/tables/open-table/candidate-preview?participant_id=member",
        json={"limit": 3},
    )

    assert preview.status_code == 200
    assert "opted-out" not in {item["participant_id"] for item in preview.json()["selected"]}
    assert "opted-out" in preview.json()["unmatched_participant_ids"]
    assert confirmed.status_code == 201
    assert "opted-out" not in confirmed.json()["state"]["participants"]
    assert source_preview.status_code == 200
    assert "opted-out" not in {
        item["participant_id"] for item in source_preview.json()["selected"]
    }
    assert candidate_preview.status_code == 200
    assert "opted-out" not in {
        item["participant_id"] for item in candidate_preview.json()["candidates"]
    }


def test_saved_opt_in_overrides_a_stale_opted_out_match_seed() -> None:
    repository = InMemoryTableRepository()
    repository.set_account_invitation_preference("current", InvitationPreference.MANY)
    client = TestClient(create_app(repository))
    stale_current = {**_seed("current"), "roundtable_invite_preference": "none"}

    response = client.post(
        "/matches/preview",
        json={
            "core_question": "Q",
            "table_size": 2,
            "candidates": [stale_current, _seed("other")],
        },
    )

    assert response.status_code == 200
    assert {item["participant_id"] for item in response.json()["selected"]} == {
        "current",
        "other",
    }


def test_source_confirmation_rechecks_preference_changed_after_preview() -> None:
    repository = InMemoryTableRepository()
    source = _Source([_seed("candidate-1"), _seed("candidate-2", "研究员")])
    client = TestClient(create_app(repository, candidate_source=source))
    preview = client.post(
        "/matches/source-preview",
        json={"core_question": "Q", "table_size": 2, "limit": 2},
    )
    assert preview.status_code == 200
    repository.set_account_invitation_preference(
        preview.json()["selected"][0]["participant_id"],
        InvitationPreference.NONE,
    )

    confirm = client.post(
        "/matches/source-confirm",
        json={"preview_token": preview.json()["preview_token"], "table_id": "late-opt-out"},
    )

    assert confirm.status_code == 409
    assert "disabled invitations after preview" in confirm.json()["detail"]
    with pytest.raises(KeyError):
        repository.get("late-opt-out")


def test_account_opt_out_blocks_unsolicited_invites_but_not_self_initiated_join() -> None:
    repository = InMemoryTableRepository()
    repository.create("join", "Q", [ParticipantSeed.model_validate(_seed("member"))])
    repository.set_account_invitation_preference("candidate", InvitationPreference.NONE)
    client = TestClient(create_app(repository))

    invitation = client.post(
        "/tables/join/invitations?inviter_id=member",
        json={"candidate": _seed("candidate"), "reason": "主动邀请"},
    )
    join_request = client.post(
        "/tables/join/join-requests?participant_id=candidate",
        json={"request_id": "self-join", "candidate": _seed("candidate")},
    )
    approved = client.post(
        "/tables/join/join-requests/self-join/approve?participant_id=member",
        json={"reason": "回应主动申请"},
    )

    assert invitation.status_code == 409
    assert "disabled" in invitation.json()["detail"]
    assert join_request.status_code == 201
    assert approved.status_code == 200
    invitation_id = approved.json()["invitation"]["invitation_id"]
    accepted = client.post(
        f"/tables/join/invitations/{invitation_id}/respond?participant_id=candidate",
        json={"accept": True},
    )
    assert accepted.status_code == 200
    assert "candidate" in accepted.json()["state"]["participants"]


def test_account_preference_persists_and_rejects_malformed_snapshot(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    repository = JsonTableRepository(path)
    repository.set_account_invitation_preference("candidate", InvitationPreference.NONE)

    restored = JsonTableRepository(path)
    assert restored.account_invitation_preference("candidate") is InvitationPreference.NONE
    assert json.loads(path.read_text(encoding="utf-8"))["invitation_preferences"] == {
        "candidate": "none"
    }

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["invitation_preferences"] = {"candidate": "invalid"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid invitation preference"):
        JsonTableRepository(path)
