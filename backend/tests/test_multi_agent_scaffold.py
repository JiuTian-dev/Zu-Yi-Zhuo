import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain import (
    HumanTurn,
    InterventionProposal,
    ParticipantSeed,
    StageSummary,
    StageSummaryDraft,
    StageSummaryFeedback,
    SummaryVerification,
)
from app.orchestrator import (
    CheckpointPolicy,
    InMemoryAgentRunLeaseStore,
    SQLiteAgentRunLeaseStore,
    TableRunCoordinator,
    build_agent_context,
    build_fallback_summary_draft,
    build_initial_state,
)
from app.orchestrator.agents import StructuredSpecialist


def state():
    return build_initial_state(
        "table-1",
        "AI Agent 进企业卡在哪？",
        [
            ParticipantSeed(participant_id="p1", display_name="甲", role="产品", declared_position="先试点"),
            ParticipantSeed(participant_id="p2", display_name="乙", role="采购", declared_position="先审计"),
        ],
    )


def turns(count: int = 4) -> list[HumanTurn]:
    return [
        HumanTurn(turn_id=index, participant_id="p1" if index % 2 else "p2", text=f"观点 {index}")
        for index in range(1, count + 1)
    ]


def draft() -> StageSummaryDraft:
    return StageSummaryDraft(
        input_state_version=4,
        phase="explore",
        trigger="thread_advanced",
        covered_turn_start=1,
        covered_turn_end=4,
        clarified=[{"text": "试点边界需要明确", "evidence_turns": [1]}],
        disagreements=[{
            "text": "先试点还是先审计",
            "evidence_turns": [1, 2],
            "disagreement_type": "value_conflict",
            "participant_ids": ["p1", "p2"],
        }],
    )


def published_summary() -> StageSummary:
    return StageSummary(
        **draft().model_dump(),
        summary_id="summary-1",
        table_id="table-1",
        revision=1,
        published_state_version=5,
        created_at=1.0,
        model="deterministic",
    )


def test_new_table_snapshot_remains_backward_compatible() -> None:
    payload = state().model_dump(mode="json", exclude_none=True)
    assert "latest_stage_summary_id" not in payload
    assert "latest_stage_summary_revision" not in payload


def test_table_summary_reference_is_atomic() -> None:
    with pytest.raises(ValidationError, match="must be set together"):
        state().model_copy(update={"latest_stage_summary_id": "summary-1"}).model_validate(
            {**state().model_dump(), "latest_stage_summary_id": "summary-1"}
        )


def test_proposal_requires_evidence_and_pass_target() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        InterventionProposal(input_state_version=4, action="PROBE", rationale="追问", confidence=0.8)
    with pytest.raises(ValidationError, match="target"):
        InterventionProposal(
            input_state_version=4, action="PASS", rationale="递话", evidence_turns=[2], confidence=0.8
        )


def test_summary_contracts_fail_closed() -> None:
    with pytest.raises(ValidationError, match="advance"):
        StageSummary(
            **draft().model_dump(), summary_id="s", revision=1,
            table_id="table-1", published_state_version=4, created_at=1.0, model="test",
        )
    with pytest.raises(ValidationError, match="known defects"):
        SummaryVerification(
            decision="approved", evidence_complete=False, attribution_safe=True,
        )
    with pytest.raises(ValidationError):
        StageSummaryFeedback(
            feedback_id="f1", table_id="table-1", summary_id="s", summary_revision=1,
            participant_id="p1", kind="misrepresented", created_at=1.0,
        )
    with pytest.raises(ValidationError, match="covered turn range"):
        StageSummaryDraft(
            input_state_version=4, phase="explore", trigger="manual",
            covered_turn_start=2, covered_turn_end=4,
            clarified=[{"text": "范围外证据", "evidence_turns": [1]}],
        )


def test_context_contains_only_uncovered_bounded_delta() -> None:
    summary = published_summary()
    current = state().model_copy(update={
        "version": 6,
        "latest_stage_summary_id": summary.summary_id,
        "latest_stage_summary_revision": summary.revision,
    })
    context = build_agent_context(current, turns(8), latest_summary=summary, max_delta_turns=3)
    assert [turn.turn_id for turn in context.delta_turns] == [6, 7, 8]
    assert context.input_state_version == 6


def test_checkpoint_policy_and_coordinator_plan_are_deterministic() -> None:
    context = build_agent_context(state().model_copy(update={"version": 4}), turns())
    decision = CheckpointPolicy().evaluate(context.delta_turns)
    plan = TableRunCoordinator().plan(context, semantic_trigger="thread_advanced")
    assert decision.eligible and decision.trigger is None
    assert plan.input_state_version == 4
    assert plan.specialist_roles[-2:] == ("stage_summarizer", "summary_verifier")
    short_context = build_agent_context(state(), turns(1))
    assert TableRunCoordinator().plan(short_context, manual_checkpoint=True).checkpoint.trigger == "manual"


def test_fallback_summary_never_invents_claims() -> None:
    fallback = build_fallback_summary_draft(state(), tuple(turns()), trigger="manual")
    assert fallback.covered_turn_start == 1
    assert fallback.covered_turn_end == 4
    assert not fallback.clarified and not fallback.disagreements and not fallback.missing


def test_in_memory_lease_is_single_flight_and_reusable() -> None:
    store = InMemoryAgentRunLeaseStore()

    async def exercise() -> list[bool]:
        first = await store.claim("table-1", 4)
        duplicate = await store.claim("table-1", 4)
        await store.release("table-1", 4)
        reclaimed = await store.claim("table-1", 4)
        return [first, duplicate, reclaimed]

    assert asyncio.run(exercise()) == [True, False, True]


def test_sqlite_lease_is_single_flight_across_instances(tmp_path: Path) -> None:
    first = SQLiteAgentRunLeaseStore(tmp_path / "leases.sqlite", owner_id="worker-a")
    second = SQLiteAgentRunLeaseStore(tmp_path / "leases.sqlite", owner_id="worker-b")

    async def exercise() -> list[bool]:
        return await asyncio.gather(
            first.claim("table-1", 4),
            second.claim("table-1", 4),
        )

    result = asyncio.run(exercise())
    assert sorted(result) == [False, True]
    asyncio.run(first.release("table-1", 4))
    asyncio.run(second.release("table-1", 4))


class BrokenProvider:
    async def structured(self, task, messages, schema, config=None):
        return {"not": "valid"}

    async def text(self, task, messages, config=None):
        return "unused"


def test_structured_specialist_uses_typed_fallback_after_one_retry() -> None:
    specialist = StructuredSpecialist(
        role="stage_summarizer",
        task="summarize checkpoint",
        schema=StageSummaryDraft,
        fallback_factory=lambda context: build_fallback_summary_draft(
            context.table_state, context.delta_turns, trigger="manual"
        ),
    )
    result = asyncio.run(specialist.run(BrokenProvider(), build_agent_context(state(), turns())))
    assert result.attempts == 2
    assert result.used_fallback
    assert result.value.covered_turn_end == 4
