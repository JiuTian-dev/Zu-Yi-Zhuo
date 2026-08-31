import pytest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import HumanTurn, ParticipantSeed


def client_and_repo() -> tuple[TestClient, InMemoryTableRepository]:
    repository = InMemoryTableRepository()
    return TestClient(create_app(repository)), repository


def participant(participant_id: str = "p1") -> dict[str, str]:
    return {
        "participant_id": participant_id,
        "display_name": "甲",
        "role": "产品",
        "declared_position": "先验证价值",
    }


def test_table_lifecycle_returns_serializable_snapshots_and_close_artifact() -> None:
    client, repository = client_and_repo()
    created = client.post("/tables", json={"table_id": "t-api", "core_question": "如何开始？"})
    assert created.status_code == 201 and created.json()["version"] == 0

    joined = client.post("/tables/t-api/participants", json=participant())
    assert joined.status_code == 200 and joined.json()["version"] == 1
    assert client.get("/tables/t-api/state").json() == joined.json()

    repository.append_turn("t-api", HumanTurn(turn_id=1, participant_id="p1", text="我亲历过一次试点。"))
    replay = client.get("/tables/t-api/replay")
    payload = replay.json()
    assert replay.status_code == 200 and [item["version"] for item in payload["snapshots"]] == [0, 1, 2]
    assert payload["messages"] == [{"turn_id": 1, "participant_id": "p1", "text": "我亲历过一次试点。"}]
    filtered = client.get("/tables/t-api/replay?from_version=1").json()
    assert [item["version"] for item in filtered["snapshots"]] == [1, 2]

    closed = client.post("/tables/t-api/close")
    assert closed.status_code == 200
    assert closed.json()["table_id"] == "t-api" and closed.json()["state_version"] == 3
    assert client.get("/tables/t-api/state").json()["conversation"]["closed"] is True
    assert client.post("/tables/t-api/close").json()["state_version"] == 3
    assert repository.get("t-api").phase.value == "close"
    with pytest.raises(ValueError, match="table is closed"):
        repository.append_turn("t-api", HumanTurn(turn_id=2, participant_id="p1", text="不应再写入"))


def test_close_artifacts_can_be_retrieved_after_close() -> None:
    client, repository = client_and_repo()
    client.post("/tables", json={"table_id": "artifact-api", "core_question": "如何开始？"})
    client.post("/tables/artifact-api/participants", json=participant("p1"))
    repository.append_turn(
        "artifact-api", HumanTurn(turn_id=1, participant_id="p1", text="我会先做一次小范围试点。")
    )
    assert client.post("/tables/artifact-api/close").status_code == 200

    response = client.get("/tables/artifact-api/close-artifacts?participant_id=p1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["table_id"] == "artifact-api"
    assert payload["state_version"] == payload["shared_baseline"]["state_version"] == payload["personal_card"]["state_version"]
    assert payload["personal_card"]["participant_id"] == "p1"
    assert payload["shared_baseline"]["collective_next_steps"][0]["is_commitment"] is True


def test_close_artifacts_require_closed_table_and_known_participant() -> None:
    client, _ = client_and_repo()
    client.post("/tables", json={"table_id": "open-artifact", "core_question": "Q", "participants": [participant("p1")]})
    assert client.get("/tables/open-artifact/close-artifacts?participant_id=p1").status_code == 409
    assert client.get("/tables/open-artifact/close-artifacts?participant_id=ghost").status_code == 409


def test_follow_up_outcomes_can_be_reported_and_retrieved_after_close() -> None:
    client, repository = client_and_repo()
    client.post("/tables", json={
        "table_id": "echo-api", "core_question": "如何开始？",
        "participants": [participant("p1"), participant("p2")],
    })
    repository.append_turn(
        "echo-api", HumanTurn(turn_id=1, participant_id="p1", text="我会先做一次小范围试点。")
    )
    assert client.post("/tables/echo-api/close").status_code == 200

    pending = client.get("/tables/echo-api/follow-ups?participant_id=p1")
    assert pending.status_code == 200
    assert pending.json()[0]["follow_up_index"] == 0
    assert pending.json()[0]["item"]["is_commitment"] is True
    assert pending.json()[0]["outcome"] is None

    reported = client.post(
        "/tables/echo-api/follow-ups/0/outcome?participant_id=p1",
        json={"status": "completed", "note": "已完成第一轮验证"},
    )
    assert reported.status_code == 200
    assert reported.json()["outcome"] == {
        "table_id": "echo-api", "follow_up_index": 0, "participant_id": "p1",
        "status": "completed", "note": "已完成第一轮验证",
    }
    assert client.get("/tables/echo-api/follow-ups?participant_id=p2").json()[0]["outcome"]["status"] == "completed"


def test_follow_up_outcome_enforces_closed_table_owner_and_index() -> None:
    client, repository = client_and_repo()
    client.post("/tables", json={
        "table_id": "echo-auth", "core_question": "Q",
        "participants": [participant("p1"), participant("p2")],
    })
    repository.append_turn("echo-auth", HumanTurn(turn_id=1, participant_id="p1", text="我会跟进这个问题。"))
    assert client.post(
        "/tables/echo-auth/follow-ups/0/outcome?participant_id=p1",
        json={"status": "completed"},
    ).status_code == 409
    client.post("/tables/echo-auth/close")
    assert client.post(
        "/tables/echo-auth/follow-ups/0/outcome?participant_id=p2",
        json={"status": "completed"},
    ).status_code == 403
    assert client.post(
        "/tables/echo-auth/follow-ups/9/outcome?participant_id=p1",
        json={"status": "completed"},
    ).status_code == 404


def test_table_directory_defaults_to_open_public_projections() -> None:
    client, repository = client_and_repo()
    client.post("/tables", json={
        "table_id": "open-table",
        "core_question": "公开问题",
        "participants": [{
            **participant("p1"),
            "declared_position": "桌内私有立场",
            "relevant_experience": [{"text": "桌内经历", "source_ref": "private:1"}],
        }],
    })
    client.post("/tables", json={
        "table_id": "closed-table", "core_question": "另一个问题", "participants": [participant("p2")],
    })
    repository.append_turn("closed-table", HumanTurn(turn_id=1, participant_id="p2", text="我亲历过一次试点。"))
    repository.close_table("closed-table")

    open_tables = client.get("/tables")
    assert open_tables.status_code == 200
    assert [item["table_id"] for item in open_tables.json()] == ["open-table"]
    assert open_tables.json()[0]["participants"]["p1"]["declared_position"] is None
    assert open_tables.json()[0]["participants"]["p1"]["unused_relevant_experience"] == []

    all_tables = client.get("/tables?include_closed=true&participant_id=p2").json()
    assert {item["table_id"] for item in all_tables} == {"open-table", "closed-table"}
    assert next(item for item in all_tables if item["table_id"] == "open-table")["participants"]["p1"]["declared_position"] is None
    assert next(item for item in all_tables if item["table_id"] == "closed-table")["conversation"]["closed"] is True


def test_api_rejects_unknown_tables_duplicate_participants_and_empty_close() -> None:
    client, _ = client_and_repo()
    assert client.get("/tables/missing").status_code == 404
    assert client.get("/tables/missing/replay?from_version=9").status_code == 404
    assert client.post("/tables", json={"table_id": "empty", "core_question": "Q"}).status_code == 201
    assert client.post("/tables/empty/close").status_code == 409
    assert client.get("/tables/empty/replay?from_version=1").status_code == 404
    assert client.get("/tables/empty/replay?from_version=-1").status_code == 422
    assert client.post("/tables/empty/participants", json=participant()).status_code == 200
    assert client.post("/tables/empty/participants", json=participant()).status_code == 409


def test_table_capacity_is_capped_at_five_seats() -> None:
    client, _ = client_and_repo()
    seats = [participant(f"p{index}") for index in range(5)]
    assert client.post(
        "/tables", json={"table_id": "full", "core_question": "Q", "participants": seats}
    ).status_code == 201
    assert client.post("/tables/full/participants", json=participant("p6")).json() == {
        "detail": "table cannot exceed 5 participants"
    }
    assert client.post(
        "/tables", json={"table_id": "too-many", "core_question": "Q", "participants": seats + [participant("p6")]}
    ).status_code == 409


def test_invitation_acceptance_cannot_overfill_a_table() -> None:
    client, _ = client_and_repo()
    seats = [participant(f"p{index}") for index in range(4)]
    assert client.post(
        "/tables", json={"table_id": "invite-full", "core_question": "Q", "participants": seats}
    ).status_code == 201
    candidate = {**participant("p6"), "display_name": "候补"}
    invitation = client.post(
        "/tables/invite-full/invitations?inviter_id=p0",
        json={"candidate": candidate, "reason": "补充视角"},
    )
    assert invitation.status_code == 201
    assert client.post("/tables/invite-full/participants", json=participant("p4")).status_code == 200

    response = client.post(
        f"/tables/invite-full/invitations/{invitation.json()['invitation_id']}/respond?participant_id=p6",
        json={"accept": True},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "table cannot exceed 5 participants"}


def test_invitation_preview_is_redacted_and_acceptance_adds_the_candidate() -> None:
    client, _ = client_and_repo()
    assert client.post(
        "/tables", json={"table_id": "invite", "core_question": "Q", "participants": [participant("p1")]}
    ).status_code == 201
    candidate = {
        **participant("p2"),
        "display_name": "乙",
        "role": "采购负责人",
        "declared_position": "只给本人看的立场",
        "relevant_experience": [{"text": "私有采购经历", "source_ref": "private:invite"}],
    }
    created = client.post(
        "/tables/invite/invitations?inviter_id=p1",
        json={"candidate": candidate, "reason": "这桌还缺采购现场视角"},
    )
    assert created.status_code == 201
    preview = created.json()
    assert preview == {
        "invitation_id": "invite:invite:1",
        "table_id": "invite",
        "participant_id": "p2",
        "display_name": "乙",
        "role": "采购负责人",
        "reason": "这桌还缺采购现场视角",
        "status": "pending",
    }
    assert "私有采购经历" not in created.text
    assert client.get("/tables/invite/invitations?participant_id=p2").json() == [preview]

    forbidden = client.post(
        "/tables/invite/invitations/invite:invite:1/respond?participant_id=p1",
        json={"accept": True},
    )
    assert forbidden.status_code == 403

    accepted = client.post(
        "/tables/invite/invitations/invite:invite:1/respond?participant_id=p2",
        json={"accept": True},
    )
    assert accepted.status_code == 200
    assert accepted.json()["invitation"]["status"] == "accepted"
    assert accepted.json()["state"]["version"] == 1
    assert accepted.json()["state"]["participants"]["p2"]["declared_position"] == "只给本人看的立场"
    assert client.post(
        "/tables/invite/invitations/invite:invite:1/respond?participant_id=p2",
        json={"accept": True},
    ).json()["state"]["version"] == 1
    assert client.post(
        "/tables/invite/invitations?inviter_id=p1", json={"candidate": candidate, "reason": "重复邀请"}
    ).status_code == 409


def test_declined_invitation_is_not_reissued_to_the_same_candidate() -> None:
    client, _ = client_and_repo()
    client.post("/tables", json={"table_id": "decline", "core_question": "Q", "participants": [participant("p1")]})
    candidate = {**participant("p3"), "display_name": "丙", "role": "研究员"}
    invite = client.post(
        "/tables/decline/invitations?inviter_id=p1",
        json={"candidate": candidate, "reason": "想听听你的研究视角"},
    )
    invitation_id = invite.json()["invitation_id"]
    declined = client.post(
        f"/tables/decline/invitations/{invitation_id}/respond?participant_id=p3",
        json={"accept": False},
    )
    assert declined.status_code == 200
    assert declined.json()["invitation"]["status"] == "declined"
    assert declined.json()["state"] is None
    assert client.get("/tables/decline/invitations?participant_id=p3").json()[0]["status"] == "declined"
    assert client.post(
        "/tables/decline/invitations?inviter_id=p1",
        json={"candidate": candidate, "reason": "再邀请不应发生"},
    ).status_code == 409
    assert client.post(
        f"/tables/decline/invitations/{invitation_id}/respond?participant_id=p3",
        json={"accept": False},
    ).status_code == 200


def test_invitation_respects_candidate_opt_out_preference() -> None:
    client, _ = client_and_repo()
    client.post("/tables", json={
        "table_id": "opt-out", "core_question": "Q", "participants": [participant("p1")],
    })
    candidate = {
        **participant("p2"),
        "roundtable_invite_preference": "none",
    }
    response = client.post(
        "/tables/opt-out/invitations?inviter_id=p1",
        json={"candidate": candidate, "reason": "不应创建"},
    )
    assert response.status_code == 409
    assert "disabled" in response.json()["detail"]


def test_sync_mode_defaults_async_and_upgrades_only_after_two_hard_conditions() -> None:
    client, repository = client_and_repo()
    client.post("/tables", json={
        "table_id": "sync",
        "core_question": "Q",
        "participants": [participant("p1"), participant("p2")],
    })
    assert client.get("/tables/sync/state").json()["conversation"]["mode"] == "async"
    repository.append_turn("sync", HumanTurn(turn_id=1, participant_id="p1", text="我亲历过一次试点。"))
    repository.append_turn("sync", HumanTurn(turn_id=2, participant_id="p2", text="我也补充一条现场经验。"))

    not_ready = client.post(
        "/tables/sync/sync/preview?participant_id=p1",
        json={"wants_continue": False, "sync_extra_value": True},
    )
    assert not_ready.status_code == 200
    assert not_ready.json()["eligible"] is False
    assert not_ready.json()["active_member_count"] == 2

    upgraded = client.post(
        "/tables/sync/sync/upgrade?participant_id=p1",
        json={
            "wants_continue": True,
            "sync_extra_value": True,
            "discussion_quality": True,
        },
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["decision"]["eligible"] is True
    assert upgraded.json()["state"]["conversation"]["mode"] == "sync"
    assert upgraded.json()["state"]["version"] == 3

    repeated = client.post(
        "/tables/sync/sync/upgrade?participant_id=p1",
        json={"wants_continue": False, "sync_extra_value": False},
    )
    assert repeated.status_code == 200
    assert repeated.json()["state"]["version"] == 3
    assert client.post(
        "/tables/sync/sync/preview?participant_id=ghost",
        json={"wants_continue": True, "sync_extra_value": True},
    ).status_code == 403


def test_repository_rejects_unknown_participants_and_invalid_turn_order() -> None:
    repository = InMemoryTableRepository()
    repository.create("turns", "Q", [])
    try:
        repository.append_turn("turns", HumanTurn(turn_id=1, participant_id="ghost", text="你好"))
    except ValueError as error:
        assert "unknown participant" in str(error)
    else:
        raise AssertionError("unknown participant was accepted")


def test_repository_replay_and_turns_are_isolated_from_callers() -> None:
    repository = InMemoryTableRepository()
    repository.create("copies", "Q", [ParticipantSeed.model_validate(participant())])
    repository.append_turn("copies", HumanTurn(turn_id=1, participant_id="p1", text="原始消息"))

    snapshots = repository.replay("copies")
    messages = repository.turns("copies")
    snapshots[0].core_question = "篡改后的问题"
    messages[0].text = "篡改后的消息"

    assert repository.replay("copies")[0].core_question == "Q"
    assert repository.turns("copies")[0].text == "原始消息"


def test_repository_get_is_isolated_from_callers() -> None:
    repository = InMemoryTableRepository()
    repository.create("current", "Q", [])
    state = repository.get("current")
    state.core_question = "篡改后的问题"

    assert repository.get("current").core_question == "Q"


def test_profile_fields_are_hidden_until_explicit_consent() -> None:
    client, _ = client_and_repo()
    created = client.post("/tables", json={
        "table_id": "privacy",
        "core_question": "Q",
        "participants": [
            {
                **participant("p1"),
                "declared_position": "只对本人可见的立场",
                "relevant_experience": [{"text": "未公开采购经历", "source_ref": "private:1"}],
            },
            {
                **participant("p2"),
                "declared_position": "另一份私有立场",
                "relevant_experience": [{"text": "另一份经历", "source_ref": "private:2"}],
            },
        ],
    })
    assert created.status_code == 201
    assert created.json()["participants"]["p1"]["declared_position"] is None
    assert created.json()["participants"]["p1"]["unused_relevant_experience"] == []

    own_view = client.get("/tables/privacy/state?participant_id=p1").json()
    assert own_view["participants"]["p1"]["declared_position"] == "只对本人可见的立场"
    assert own_view["participants"]["p1"]["unused_relevant_experience"][0]["source_ref"] == "private:1"
    assert own_view["participants"]["p2"]["declared_position"] is None

    consented = client.post(
        "/tables/privacy/participants/p2/consent?viewer_id=p2",
        json={"profile_shared": True},
    )
    assert consented.status_code == 200
    assert consented.json()["participants"]["p2"]["declared_position"] == "另一份私有立场"
    public_view = client.get("/tables/privacy/state").json()
    assert public_view["participants"]["p2"]["declared_position"] == "另一份私有立场"
    assert public_view["participants"]["p2"]["unused_relevant_experience"][0]["source_ref"] == "private:2"

    revoked = client.post(
        "/tables/privacy/participants/p2/consent?viewer_id=p2",
        json={"profile_shared": False},
    )
    assert revoked.status_code == 200
    assert client.get("/tables/privacy/state").json()["participants"]["p2"]["declared_position"] is None


def test_rest_consent_is_self_scoped() -> None:
    client, _ = client_and_repo()
    response = client.post("/tables/privacy/participants/p2/consent?viewer_id=p1", json={"profile_shared": True})

    assert response.status_code == 404  # the table is absent; no identity detail is disclosed

    client.post("/tables", json={
        "table_id": "privacy-self",
        "core_question": "Q",
        "participants": [participant("p1"), participant("p2")],
    })
    response = client.post(
        "/tables/privacy-self/participants/p2/consent?viewer_id=p1",
        json={"profile_shared": True},
    )
    assert response.status_code == 403
    assert client.get("/tables/privacy-self/state").json()["participants"]["p2"]["declared_position"] is None


def test_match_preview_returns_public_seats_and_explainable_reasons() -> None:
    client, _ = client_and_repo()
    candidates = [
        {
            "participant_id": "tech",
            "display_name": "技术角色",
            "role": "AI 架构师",
            "declared_position": "模型精度是关键",
            "relevant_experience": [{"text": "做过企业 Agent 落地", "source_ref": "private:tech"}],
        },
        {
            "participant_id": "buyer",
            "display_name": "采购角色",
            "role": "企业采购负责人",
            "declared_position": "采购责任链是关键",
            "relevant_experience": [{"text": "亲历过供应商采购", "source_ref": "private:buyer"}],
        },
        {
            "participant_id": "product",
            "display_name": "产品角色",
            "role": "产品负责人",
            "declared_position": "价值闭环更重要",
        },
    ]
    response = client.post("/matches/preview", json={
        "core_question": "AI Agent 进入企业卡在哪里？",
        "candidates": candidates,
        "table_size": 3,
    })
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["selected"]) == 3
    assert {seat["participant_id"] for seat in payload["selected"]} == {"tech", "buyer", "product"}
    assert {reason["participant_id"] for reason in payload["reasons"]} == {"tech", "buyer", "product"}
    assert all("declared_position" not in seat and "relevant_experience" not in seat for seat in payload["selected"])
    serialized = response.text
    assert "模型精度是关键" not in serialized
    assert "private:tech" not in serialized


def test_match_confirm_creates_a_table_from_the_same_public_match_plan() -> None:
    client, _ = client_and_repo()
    candidates = [
        {**participant("p1"), "role": "架构师", "relevant_experience": [{"text": "做过 Agent 试点", "source_ref": "private:1"}]},
        {**participant("p2"), "role": "采购负责人", "relevant_experience": [{"text": "做过供应商采购", "source_ref": "private:2"}]},
        {**participant("p3"), "role": "产品负责人"},
    ]
    response = client.post("/matches/confirm", json={
        "table_id": "matched-table", "core_question": "Agent 试点如何进入企业？",
        "candidates": candidates, "table_size": 3,
    })
    assert response.status_code == 201
    payload = response.json()
    assert payload["plan"]["core_question"] == payload["state"]["core_question"]
    assert {seat["participant_id"] for seat in payload["plan"]["selected"]} == {"p1", "p2", "p3"}
    assert set(payload["state"]["participants"]) == {"p1", "p2", "p3"}
    assert payload["state"]["participants"]["p1"]["declared_position"] is None
    assert client.post("/matches/confirm", json={
        "table_id": "matched-table", "core_question": "Q", "candidates": candidates, "table_size": 3,
    }).status_code == 409


def test_health_and_readiness_probes_are_available() -> None:
    client = TestClient(create_app())

    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {
        "status": "ready",
        "repository": "InMemoryTableRepository",
    }


def test_default_cors_allows_vite_dev_origin() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/healthz",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
