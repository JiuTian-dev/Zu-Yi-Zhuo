from app.domain import HumanTurn, ParticipantSeed, StageSummaryDraft
from app.orchestrator import build_agent_context, build_initial_state
from app.orchestrator.agents.verify import verify_summary_draft


def context():
    state = build_initial_state("table-1", "AI 和朋友的区别？", [
        ParticipantSeed(participant_id="p1", display_name="甲", role="成员", declared_position="未定"),
        ParticipantSeed(participant_id="p2", display_name="乙", role="成员", declared_position="未定"),
        ParticipantSeed(participant_id="p3", display_name="丙", role="成员", declared_position="未定"),
    ])
    turns = [
        HumanTurn(turn_id=1, participant_id="p1", text="我有时候会跟 AI 聊。"),
        HumanTurn(turn_id=2, participant_id="p2", text="我觉得朋友也很重要。"),
    ]
    return build_agent_context(state, turns)


def draft(**changes):
    values = {
        "input_state_version": context().input_state_version,
        "phase": context().table_state.phase,
        "trigger": "manual", "covered_turn_start": 1, "covered_turn_end": 2,
        "clarified": [{"text": "甲有时候会跟 AI 聊。", "evidence_turns": [1]}],
    }
    values.update(changes)
    return StageSummaryDraft(**values)


def test_verifier_rejects_unspoken_consensus_even_when_turn_ids_exist():
    result = verify_summary_draft(draft(clarified=[
        {"text": "大家一致认为 AI 可以替代朋友。", "evidence_turns": [1, 2]},
    ]), context())
    assert result.decision == "reject"
    assert "collective agreement" in " ".join(result.unsupported_claims)


def test_verifier_rejects_disagreement_attributed_to_uncited_speaker():
    result = verify_summary_draft(draft(disagreements=[{
        "text": "甲与丙意见相反。", "evidence_turns": [1, 2],
        "participant_ids": ["p1", "p3"], "disagreement_type": "value_conflict",
    }]), context())
    assert result.decision == "reject" and not result.attribution_safe


def test_verifier_rejects_empty_or_oversized_checkpoint():
    assert verify_summary_draft(draft(clarified=[]), context()).decision == "reject"
    assert verify_summary_draft(draft(clarified=[{
        "text": "字" * 481, "evidence_turns": [1],
    }]), context()).decision == "reject"


def test_verifier_rejects_internal_participant_labels_in_public_text():
    assert verify_summary_draft(draft(clarified=[{
        "text": "甲（guest）更在意即时回应。", "evidence_turns": [1],
    }]), context()).decision == "reject"
    assert verify_summary_draft(draft(clarified=[{
        "text": "参与者 p1 更在意即时回应。", "evidence_turns": [1],
    }]), context()).decision == "reject"


def test_verifier_allows_short_attributed_statement_with_matching_snapshot():
    assert verify_summary_draft(draft(), context()).decision == "approved"
