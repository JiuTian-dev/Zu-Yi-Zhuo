import asyncio

from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed
from app.orchestrator.run_service import TableRunService


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


async def _collect(target: list, value) -> None:
    target.append(value)

