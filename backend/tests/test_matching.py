import pytest
from pydantic import ValidationError

from app.demo import flagship_participants
from app.domain import MatchRequest, ParticipantSeed
from app.matching import build_match_plan


QUESTION = "AI Agent 真正进入企业，卡住的是技术还是采购？"


def test_match_plan_is_stable_varied_and_private_profile_free() -> None:
    request = MatchRequest(core_question=QUESTION, candidates=flagship_participants, table_size=4)
    first = build_match_plan(request)
    second = build_match_plan(request)

    assert first == second
    assert len(first.selected) == 4
    assert len({seat.role for seat in first.selected}) == 4
    assert {reason.participant_id for reason in first.reasons} == {
        seat.participant_id for seat in first.selected
    }
    assert all(not hasattr(seat, "declared_position") for seat in first.selected)
    assert all(not hasattr(seat, "relevant_experience") for seat in first.selected)


def test_match_plan_still_forms_a_group_when_question_has_no_known_terms() -> None:
    request = MatchRequest(core_question="一个值得慢慢聊的问题", candidates=flagship_participants, table_size=3)
    plan = build_match_plan(request)
    assert len(plan.selected) == 3
    assert all(reason.reason for reason in plan.reasons)


def test_match_request_rejects_duplicate_ids_and_oversized_table() -> None:
    with pytest.raises(ValidationError, match="unique"):
        MatchRequest(core_question="Q", candidates=[flagship_participants[0], flagship_participants[0]])
    with pytest.raises(ValidationError, match="exceed"):
        MatchRequest(core_question="Q", candidates=flagship_participants[:2], table_size=3)


def test_match_respects_candidate_invitation_opt_out() -> None:
    opted_out = ParticipantSeed.model_validate({
        **flagship_participants[0].model_dump(),
        "roundtable_invite_preference": "none",
    })
    request = MatchRequest(
        core_question=QUESTION,
        candidates=[opted_out, *flagship_participants[1:]],
        table_size=4,
    )
    plan = build_match_plan(request)
    assert "architect" not in {seat.participant_id for seat in plan.selected}
    assert "architect" in plan.unmatched_participant_ids

    with pytest.raises(ValidationError, match="invitation-eligible"):
        MatchRequest(core_question="Q", candidates=[opted_out, opted_out.model_copy(update={"participant_id": "other"})], table_size=2)
