import asyncio

import pytest

from app.api.repository import InMemoryTableRepository
from app.domain import ContentAnalysis, ParticipantSeed, ParticipationAnalysis, StageSummaryDraft, SummaryVerification
from app.orchestrator.run_service import TableRunService


class _HangingProvider:
    model = "hanging-test-model"

    async def text(self, task, messages, config=None):
        await asyncio.sleep(1)
        return "unreachable"

    async def structured(self, task, messages, schema, config=None):
        await asyncio.sleep(1)
        return {}


def setup_repo() -> InMemoryTableRepository:
    repo = InMemoryTableRepository()
    repo.create("table-1", "Q", [
        ParticipantSeed(participant_id="p1", display_name="甲", role="产品", declared_position="先试点"),
        ParticipantSeed(participant_id="p2", display_name="乙", role="采购", declared_position="先审计"),
    ])
    repo.append_message_once("table-1", "p1", "先讲一个案例", "m1")
    repo.append_message_once("table-1", "p2", "我补充采购约束", "m2")
    return repo


def test_run_service_publishes_manual_summary_after_message_commit() -> None:
    repo = setup_repo()
    events: list[dict] = []
    states: list[int] = []

    async def exercise() -> None:
        service = TableRunService(
            repo,
            broadcast=lambda _table_id, event: _collect(events, event),
            broadcast_state=lambda _table_id, state: _collect(states, state.version),
        )
        await service.enqueue("table-1", manual=True)
        await service.wait_idle("table-1")

    asyncio.run(exercise())
    assert [event["type"] for event in events] == ["stage_summary_started", "stage_summary_published"]
    assert states == [3]
    assert repo.latest_stage_summary("table-1").revision == 1
    assert repo.get("table-1").version == 3


def test_run_service_merges_pending_triggers_and_does_not_publish_on_budget_only() -> None:
    repo = setup_repo()
    events: list[dict] = []

    async def exercise() -> None:
        service = TableRunService(repo, broadcast=lambda _table_id, event: _collect(events, event))
        await service.enqueue("table-1")
        await service.wait_idle("table-1")

    asyncio.run(exercise())
    assert events == []
    assert repo.latest_stage_summary("table-1") is None


def test_run_service_falls_back_when_provider_exceeds_the_deadline() -> None:
    repo = setup_repo()
    events: list[dict] = []

    async def exercise() -> None:
        service = TableRunService(
            repo,
            provider=_HangingProvider(),
            broadcast=lambda _table_id, event: _collect(events, event),
            deadline_seconds=0.05,
        )
        await service.enqueue("table-1", manual=True)
        await asyncio.wait_for(service.wait_idle("table-1"), timeout=0.09)

    asyncio.run(exercise())
    assert [event["type"] for event in events] == ["stage_summary_started", "stage_summary_published"]
    summary = repo.latest_stage_summary("table-1")
    assert summary is not None and summary.used_fallback is True
    assert summary.model == "deterministic-fallback"


async def _collect(target: list, value) -> None:
    target.append(value)


class _SummaryProvider:
    model = "summary-test-model"

    def __init__(self, *, reject=False, slow_analysts=False, repair=False, invented_evidence=False):
        self.reject = reject
        self.slow_analysts = slow_analysts
        self.repair = repair
        self.invented_evidence = invented_evidence
        self.schemas = []
        self.cancelled_analysts = 0

    async def structured(self, task, messages, schema, config=None):
        self.schemas.append(schema)
        await asyncio.sleep(0)
        if schema in (ContentAnalysis, ParticipationAnalysis):
            if self.slow_analysts:
                try:
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    self.cancelled_analysts += 1
                    raise
            return {}  # Analysis failure cannot poison a verified summary.
        if schema is SummaryVerification:
            return SummaryVerification(
                decision="reject" if self.reject else "approved",
                evidence_complete=True, attribution_safe=True,
                unsupported_claims=["unsupported motive"] if self.reject else [],
            )
        if self.repair and self.schemas.count(StageSummaryDraft) == 1:
            return "invalid JSON"
        return StageSummaryDraft(
            input_state_version=777, phase="deepen", trigger="thread_advanced",
            covered_turn_start=1, covered_turn_end=99,
            clarified=[{
                "text": "甲想先讲一个案例，乙补充了采购约束。",
                "evidence_turns": [99] if self.invented_evidence else [1, 2],
            }],
        )


def test_model_summary_metadata_is_bound_by_code_and_analysis_failure_does_not_block_it() -> None:
    repo = setup_repo()
    provider = _SummaryProvider(repair=True)

    async def exercise():
        service = TableRunService(repo, provider=provider)
        await service.enqueue("table-1", manual=True)
        await service.wait_idle("table-1")

    asyncio.run(exercise())
    summary = repo.latest_stage_summary("table-1")
    assert summary is not None
    assert summary.input_state_version == 2
    assert summary.trigger == "manual"
    assert summary.phase == repo.get("table-1").phase
    assert (summary.covered_turn_start, summary.covered_turn_end) == (1, 2)
    assert summary.model == provider.model and not summary.used_fallback
    assert len(provider.schemas) == 5


def test_semantic_rejection_falls_back_instead_of_publishing_invented_claim() -> None:
    repo = setup_repo()
    provider = _SummaryProvider(reject=True)

    async def exercise():
        service = TableRunService(repo, provider=provider)
        await service.enqueue("table-1", manual=True)
        await service.wait_idle("table-1")

    asyncio.run(exercise())
    summary = repo.latest_stage_summary("table-1")
    assert summary is not None and summary.used_fallback
    assert summary.model == "deterministic-fallback"
    assert not summary.clarified


def test_metadata_binding_never_rewrites_invented_evidence_into_real_turns() -> None:
    repo = setup_repo()
    provider = _SummaryProvider(invented_evidence=True)

    async def exercise():
        service = TableRunService(repo, provider=provider)
        await service.enqueue("table-1", manual=True)
        await service.wait_idle("table-1")

    asyncio.run(exercise())
    summary = repo.latest_stage_summary("table-1")
    assert summary is not None and summary.used_fallback and not summary.clarified
    assert SummaryVerification not in provider.schemas


def test_slow_independent_analysts_do_not_delay_verified_summary() -> None:
    repo = setup_repo()
    provider = _SummaryProvider(slow_analysts=True)

    async def exercise():
        service = TableRunService(repo, provider=provider, deadline_seconds=0.1)
        await service.enqueue("table-1", manual=True)
        await asyncio.wait_for(service.wait_idle("table-1"), timeout=0.3)

    asyncio.run(exercise())
    summary = repo.latest_stage_summary("table-1")
    assert summary is not None and summary.model == provider.model


def test_cancellation_clears_visible_progress_and_releases_work() -> None:
    repo = setup_repo()
    events = []

    async def exercise():
        service = TableRunService(
            repo, provider=_HangingProvider(), broadcast=lambda _, event: _collect(events, event),
        )
        await service.enqueue("table-1", manual=True)
        await asyncio.sleep(0)
        await service.close()
        assert await service.lease_store.claim("table-1", 2)
        await service.lease_store.release("table-1", 2)

    asyncio.run(exercise())
    assert [item["type"] for item in events] == ["stage_summary_started", "stage_summary_failed"]
    assert events[-1]["code"] == "cancelled"
    assert repo.latest_stage_summary("table-1") is None


def test_manual_request_without_new_turns_finishes_with_short_failure() -> None:
    repo = setup_repo()
    events = []

    async def exercise():
        service = TableRunService(repo, broadcast=lambda _, event: _collect(events, event))
        await service.enqueue("table-1", manual=True)
        await service.wait_idle("table-1")
        await service.enqueue("table-1", manual=True)
        await service.wait_idle("table-1")

    asyncio.run(exercise())
    assert events[-1]["type"] == "stage_summary_failed"
    assert events[-1]["code"] == "no_uncovered_turns"


@pytest.mark.parametrize("deadline", [0, -1, float("inf"), float("nan"), 121])
def test_summary_deadline_must_be_finite_and_bounded(deadline) -> None:
    with pytest.raises(ValueError, match="finite"):
        TableRunService(setup_repo(), deadline_seconds=deadline)
