from pathlib import Path

import pytest

from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import AgentRunRecord, ParticipantSeed, StageSummary, StageSummaryFeedback


def seed() -> list[ParticipantSeed]:
    return [
        ParticipantSeed(participant_id="p1", display_name="甲", role="产品", declared_position="先试点"),
        ParticipantSeed(participant_id="p2", display_name="乙", role="采购", declared_position="先审计"),
    ]


def publish(repo: InMemoryTableRepository, revision: int = 1) -> StageSummary:
    current = repo.get("table-1")
    summary = StageSummary(
        summary_id="summary-1",
        table_id="table-1",
        revision=revision,
        status="published",
        input_state_version=current.version,
        published_state_version=current.version + 1,
        phase=current.phase,
        trigger="manual",
        covered_turn_start=1,
        covered_turn_end=2,
        clarified=[{"text": "试点边界需要明确", "evidence_turns": [1]}],
        disagreements=[],
        missing=[],
        next_focus=None,
        created_at=1.0 + revision,
        model="deterministic",
    )
    next_state = current.model_copy(update={
        "version": current.version + 1,
        "latest_stage_summary_id": summary.summary_id,
        "latest_stage_summary_revision": summary.revision,
    })
    return summary.model_copy(update={
        "published_state_version": next_state.version,
    }) if repo.append_stage_summary_bundle("table-1", next_state, summary) else summary


def setup(repo: InMemoryTableRepository) -> None:
    repo.create("table-1", "Q", seed())
    repo.append_message_once("table-1", "p1", "观点一", "m1")
    repo.append_message_once("table-1", "p2", "观点二", "m2")


def test_summary_bundle_is_atomic_and_revisioned() -> None:
    repo = InMemoryTableRepository()
    setup(repo)
    first = publish(repo)
    assert repo.get("table-1").latest_stage_summary_revision == 1
    second = publish(repo, revision=2)
    rows = repo.stage_summaries("table-1")
    assert [item.status for item in rows] == ["superseded", "published"]
    assert second.revision == 2
    assert repo.latest_stage_summary("table-1").revision == 2


def test_summary_bundle_rejects_stale_state_without_partial_write() -> None:
    repo = InMemoryTableRepository()
    setup(repo)
    current = repo.get("table-1")
    summary = StageSummary(
        summary_id="summary-1", table_id="table-1", revision=1,
        input_state_version=current.version, published_state_version=current.version + 1,
        phase=current.phase, trigger="manual", covered_turn_start=1, covered_turn_end=2,
        clarified=[], disagreements=[], missing=[], created_at=1.0, model="test",
    )
    stale = current.model_copy(update={"version": current.version + 2})
    with pytest.raises(ValueError, match="next snapshot"):
        repo.append_stage_summary_bundle("table-1", stale, summary)
    assert repo.get("table-1").version == current.version
    assert repo.stage_summaries("table-1") == []


def test_summary_bundle_rejects_budget_and_unknown_attribution() -> None:
    repo = InMemoryTableRepository()
    setup(repo)
    current = repo.get("table-1")
    oversized = StageSummary(
        summary_id="summary-budget", table_id="table-1", revision=1,
        input_state_version=current.version, published_state_version=current.version + 1,
        phase=current.phase, trigger="manual", covered_turn_start=1, covered_turn_end=2,
        clarified=[{"text": "x" * 2401, "evidence_turns": [1]}],
        disagreements=[], missing=[], created_at=1.0, model="test",
    )
    with pytest.raises(ValueError, match="text budget"):
        repo.append_stage_summary_bundle("table-1", current.model_copy(update={
            "version": current.version + 1,
            "latest_stage_summary_id": oversized.summary_id,
            "latest_stage_summary_revision": 1,
        }), oversized)


def test_feedback_and_run_ledgers_are_idempotent_and_private() -> None:
    repo = InMemoryTableRepository()
    setup(repo)
    publish(repo)
    feedback = StageSummaryFeedback(
        feedback_id="feedback-1", table_id="table-1", summary_id="summary-1",
        summary_revision=1, participant_id="p1", kind="missing_point",
        note="还缺少失败条件", created_at=2.0,
    )
    assert repo.append_summary_feedback(feedback)[1]
    assert not repo.append_summary_feedback(feedback)[1]
    run = AgentRunRecord(
        run_id="run-1", table_id="table-1", trigger_turn_id=2,
        input_state_version=2, outcome="fallback", invoked_agents=["stage_summarizer"],
        attempts=2, latency_ms=20, used_fallback=True,
    )
    assert repo.append_agent_run(run)[1]
    assert not repo.append_agent_run(run)[1]
    assert repo.summary_feedback("table-1")[0].note == "还缺少失败条件"
    assert repo.agent_runs("table-1")[0].model_dump(mode="json")["run_id"] == "run-1"


def test_feedback_revision_supersedes_previous_summary() -> None:
    repo = InMemoryTableRepository()
    setup(repo)
    publish(repo)
    feedback = StageSummaryFeedback(
        feedback_id="feedback-1", table_id="table-1", summary_id="summary-1",
        summary_revision=1, participant_id="p1", kind="missing_point",
        note="还缺少失败条件", evidence_turns=[2], created_at=2.0,
    )
    repo.append_summary_feedback(feedback)
    revised, saved, state = repo.apply_summary_feedback_revision("table-1", "feedback-1")
    assert revised.revision == 2
    assert revised.missing[-1].text == "还缺少失败条件"
    assert saved.status == "applied"
    assert state.latest_stage_summary_revision == 2
    assert [item.status for item in repo.stage_summaries("table-1")] == ["superseded", "published"]


def test_feedback_revision_accepts_note_without_evidence_and_rejects_stale_second_edit() -> None:
    repo = InMemoryTableRepository()
    setup(repo)
    publish(repo)
    feedback = StageSummaryFeedback(
        feedback_id="feedback-note-only", table_id="table-1", summary_id="summary-1",
        summary_revision=1, participant_id="p2", kind="not_consensus",
        note="这部分还需要另一位参与者确认", created_at=2.0,
    )
    repo.append_summary_feedback(feedback)
    revised, _, _ = repo.apply_summary_feedback_revision("table-1", feedback.feedback_id)
    assert revised.missing[-1].text == feedback.note
    assert revised.missing[-1].evidence_turns == [2]
    stale = StageSummaryFeedback(
        feedback_id="feedback-stale", table_id="table-1", summary_id="summary-1",
        summary_revision=1, participant_id="p1", kind="missing_point",
        note="旧版本上的修正", evidence_turns=[1], created_at=3.0,
    )
    repo.append_summary_feedback(stale)
    with pytest.raises(ValueError, match="latest published summary"):
        repo.apply_summary_feedback_revision("table-1", stale.feedback_id)


def test_json_repository_preserves_old_snapshots_and_new_ledgers(tmp_path: Path) -> None:
    path = tmp_path / "tables.json"
    repo = JsonTableRepository(path)
    setup(repo)
    publish(repo)
    feedback = StageSummaryFeedback(
        feedback_id="feedback-1", table_id="table-1", summary_id="summary-1",
        summary_revision=1, participant_id="p1", kind="ready_to_advance", created_at=2.0,
    )
    repo.append_summary_feedback(feedback)
    reloaded = JsonTableRepository(path)
    assert reloaded.latest_stage_summary("table-1").summary_id == "summary-1"
    assert reloaded.summary_feedback("table-1")[0].kind == "ready_to_advance"
