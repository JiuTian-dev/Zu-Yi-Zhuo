import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.app import create_app
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
