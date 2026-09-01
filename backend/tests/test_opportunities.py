import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.app import create_app
from app.api.repository import JsonTableRepository
from app.domain import ContentSignal, OpportunityRequest
from app.opportunities import build_opportunity_preview


def _signal(signal_id: str, author_id: str, content_type: str, **overrides) -> dict:
    return {
        "signal_id": signal_id,
        "content_type": content_type,
        "title": "企业 Agent 如何落地？",
        "excerpt": "试点需要明确责任和验收边界。",
        "source_ref": f"zhihu:public:{signal_id}",
        "author_id": author_id,
        "author_name": author_id,
        **overrides,
    }


def test_opportunity_preview_exposes_unfinishedness_roles_and_candidates() -> None:
    request = OpportunityRequest(
        query="企业 Agent 如何落地？",
        signals=[
            ContentSignal.model_validate(_signal("s1", "u1", "question", author_role="产品", public_stance="先验证价值")),
            ContentSignal.model_validate(_signal("s2", "u2", "answer", author_role="架构师", public_stance="先解决技术边界", engagement=20)),
        ],
    )

    preview = build_opportunity_preview(request)

    assert preview.core_question == "企业 Agent 如何落地？"
    assert preview.signal_ids == ["s1", "s2"]
    assert [signal.signal_id for signal in preview.source_signals] == ["s1", "s2"]
    assert preview.source_signals[0].title == "企业 Agent 如何落地？"
    assert {candidate.participant_id for candidate in preview.candidates} == {"u1", "u2"}
    assert {
        candidate.participant_id: candidate.public_signal_ids
        for candidate in preview.candidates
    } == {"u1": ["s1"], "u2": ["s2"]}
    assert preview.unfinishedness[1].signal_ids == ["s2"]
    assert preview.role_gaps == ["实践者"]
    assert preview.confidence == 0.75


def test_opportunity_preview_can_feed_existing_match_preview() -> None:
    client = TestClient(create_app())
    response = client.post("/opportunities/preview", json={
        "query": "企业 Agent 如何落地？",
        "signals": [
            _signal("s1", "u1", "question", author_role="产品"),
            _signal("s2", "u2", "answer", author_role="架构师"),
        ],
    })
    assert response.status_code == 200
    preview = response.json()
    assert [signal["signal_id"] for signal in preview["source_signals"]] == ["s1", "s2"]
    assert preview["source_signals"][0]["source_ref"] == "zhihu:public:s1"
    assert all("relevant_experience" not in signal for signal in preview["source_signals"])
    assert all("private_stance" not in signal for signal in preview["source_signals"])
    matched = client.post("/matches/preview", json={
        "core_question": preview["core_question"],
        "candidates": preview["candidates"],
        "table_size": 2,
    })
    assert matched.status_code == 200
    assert {seat["participant_id"] for seat in matched.json()["selected"]} == {"u1", "u2"}
    assert {
        reason["participant_id"]: reason["evidence_signal_ids"]
        for reason in matched.json()["reasons"]
    } == {"u1": ["s1"], "u2": ["s2"]}


def test_match_confirmation_persists_public_origin_signal_ids_and_replays_them(tmp_path) -> None:
    repository = JsonTableRepository(tmp_path / "lineage.json")
    client = TestClient(create_app(repository))
    preview = client.post("/opportunities/preview", json={
        "query": "企业 Agent 如何落地？",
        "signals": [
            _signal("s1", "u1", "question", author_role="产品"),
            _signal("s2", "u2", "answer", author_role="架构师"),
        ],
    }).json()

    confirmed = client.post("/matches/confirm", json={
        "table_id": "lineage-table",
        "core_question": preview["core_question"],
        "candidates": preview["candidates"],
        "table_size": 2,
        "origin_signal_ids": preview["signal_ids"],
        "origin_signals": preview["source_signals"],
    })

    assert confirmed.status_code == 201
    assert confirmed.json()["state"]["origin_signal_ids"] == ["s1", "s2"]
    assert "source_signals" not in confirmed.json()["state"]
    replay = client.get("/tables/lineage-table/replay")
    assert replay.status_code == 200
    assert replay.json()["snapshots"][0]["origin_signal_ids"] == ["s1", "s2"]
    assert [signal["signal_id"] for signal in replay.json()["source_signals"]] == ["s1", "s2"]
    assert replay.json()["source_signals"][0]["source_ref"] == "zhihu:public:s1"
    assert "relevant_experience" not in replay.json()["source_signals"][0]
    assert "private_stance" not in replay.json()["source_signals"][0]

    restored = JsonTableRepository(tmp_path / "lineage.json")
    assert restored.get("lineage-table").origin_signal_ids == ["s1", "s2"]
    assert restored.replay("lineage-table")[0].origin_signal_ids == ["s1", "s2"]
    assert [signal.signal_id for signal in restored.public_source_signals("lineage-table")] == ["s1", "s2"]
    assert restored.public_source_signals("lineage-table")[0].title == "企业 Agent 如何落地？"


def test_direct_table_creation_derives_and_persists_public_source_snapshots(tmp_path) -> None:
    repository = JsonTableRepository(tmp_path / "direct-lineage.json")
    client = TestClient(create_app(repository))
    response = client.post("/tables", json={
        "table_id": "direct-lineage",
        "core_question": "Q",
        "participants": [
            {
                "participant_id": "p1",
                "display_name": "甲",
                "role": "产品",
                "declared_position": "先验证价值",
                "public_signal_ids": ["s1"],
            },
            {
                "participant_id": "p2",
                "display_name": "乙",
                "role": "技术",
                "declared_position": "先解决边界",
                "public_signal_ids": ["s2"],
            },
        ],
        "origin_signals": [_signal("s1", "p1", "question"), _signal("s2", "p2", "answer")],
    })

    assert response.status_code == 201
    assert response.json()["origin_signal_ids"] == ["s1", "s2"]
    replay = client.get("/tables/direct-lineage/replay").json()
    assert [signal["signal_id"] for signal in replay["source_signals"]] == ["s1", "s2"]
    restored = JsonTableRepository(tmp_path / "direct-lineage.json")
    assert [signal.signal_id for signal in restored.public_source_signals("direct-lineage")] == [
        "s1", "s2"
    ]


def test_origin_source_snapshot_must_match_origin_signal_ids() -> None:
    client = TestClient(create_app())
    response = client.post("/matches/confirm", json={
        "table_id": "mismatched-lineage",
        "core_question": "Q",
        "candidates": [
            {
                "participant_id": "u1",
                "display_name": "u1",
                "role": "产品",
                "declared_position": "先验证价值",
                "public_signal_ids": ["s1"],
            },
            {
                "participant_id": "u2",
                "display_name": "u2",
                "role": "技术",
                "declared_position": "先解决边界",
                "public_signal_ids": ["s2"],
            },
        ],
        "table_size": 2,
        "origin_signal_ids": ["s1"],
        "origin_signals": [_signal("s2", "u2", "answer")],
    })

    assert response.status_code == 422


def test_match_confirmation_rejects_unknown_origin_signal_ids() -> None:
    client = TestClient(create_app())
    response = client.post("/matches/confirm", json={
        "table_id": "invalid-lineage",
        "core_question": "企业 Agent 如何落地？",
        "candidates": [
            {
                "participant_id": "u1",
                "display_name": "u1",
                "role": "产品",
                "declared_position": "先验证价值",
                "public_signal_ids": ["s1"],
            },
            {
                "participant_id": "u2",
                "display_name": "u2",
                "role": "技术",
                "declared_position": "先解决边界",
                "public_signal_ids": ["s2"],
            },
        ],
        "table_size": 2,
        "origin_signal_ids": ["not-in-candidates"],
    })

    assert response.status_code == 422


def test_direct_table_creation_accepts_public_origin_signal_ids() -> None:
    client = TestClient(create_app())
    response = client.post("/tables", json={
        "table_id": "direct-lineage",
        "core_question": "Q",
        "participants": [
            {
                "participant_id": "p1",
                "display_name": "甲",
                "role": "产品",
                "declared_position": "先验证价值",
                "public_signal_ids": ["s1"],
            },
            {
                "participant_id": "p2",
                "display_name": "乙",
                "role": "技术",
                "declared_position": "先解决边界",
                "public_signal_ids": ["s2"],
            },
        ],
        "origin_signal_ids": ["s1", "s2"],
    })

    assert response.status_code == 201
    assert response.json()["origin_signal_ids"] == ["s1", "s2"]


def test_opportunity_request_rejects_duplicate_or_private_signals() -> None:
    with pytest.raises(ValidationError, match="signal_id"):
        OpportunityRequest(
            query="Q",
            signals=[
                ContentSignal.model_validate(_signal("same", "u1", "question")),
                ContentSignal.model_validate(_signal("same", "u2", "answer")),
            ],
        )

    client = TestClient(create_app())
    response = client.post("/opportunities/preview", json={
        "query": "Q",
        "signals": [
            _signal("s1", "u1", "question", visibility="private"),
            _signal("s2", "u2", "answer"),
        ],
    })
    assert response.status_code == 422


def test_opportunity_request_requires_two_public_authors() -> None:
    with pytest.raises(ValidationError, match="two authors"):
        OpportunityRequest(
            query="Q",
            signals=[
                ContentSignal.model_validate(_signal("s1", "u1", "question")),
                ContentSignal.model_validate(_signal("s2", "u1", "answer")),
            ],
        )
