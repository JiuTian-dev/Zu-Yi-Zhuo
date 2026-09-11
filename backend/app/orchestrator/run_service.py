"""Non-blocking table run lifecycle for checkpoint and specialist work."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
import time
from uuid import uuid4

from app.api.repository import InMemoryTableRepository
from app.domain import AgentRunRecord, StageSummary, StageSummaryTrigger, TableState
from app.orchestrator.agents import ContentAnalystAgent, ParticipationAnalystAgent, StageSummarizerAgent, SummaryVerifierAgent, propose_action
from app.orchestrator.checkpoint import CheckpointPolicy
from app.orchestrator.context import build_agent_context
from app.orchestrator.lease import AgentRunLeaseStore, InMemoryAgentRunLeaseStore
from app.providers.base import LLMProvider


Broadcast = Callable[[str, dict], Awaitable[None]]
BroadcastState = Callable[[str, TableState], Awaitable[None]]


class TableRunService:
    """Owns background run scheduling while keeping all state writes in the repository."""

    def __init__(
        self,
        repository: InMemoryTableRepository,
        *,
        provider: LLMProvider | None = None,
        broadcast: Broadcast | None = None,
        broadcast_state: BroadcastState | None = None,
        lease_store: AgentRunLeaseStore | None = None,
        checkpoint_policy: CheckpointPolicy | None = None,
        deadline_seconds: float = 8.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        self.repository = repository
        self.provider = provider
        self.broadcast = broadcast
        self.broadcast_state = broadcast_state
        self.lease_store = lease_store or InMemoryAgentRunLeaseStore()
        self.checkpoint_policy = checkpoint_policy or CheckpointPolicy()
        self.deadline_seconds = deadline_seconds
        self.clock = clock
        self._pending: dict[str, tuple[StageSummaryTrigger | None, bool, bool, bool]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def enqueue(
        self,
        table_id: str,
        *,
        semantic_trigger: StageSummaryTrigger | None = None,
        manual: bool = False,
        pre_close: bool = False,
        silent: bool = False,
    ) -> None:
        """Merge triggers and schedule at most one active run for a table."""
        async with self._lock:
            previous = self._pending.get(table_id)
            trigger = semantic_trigger or (previous[0] if previous else None)
            self._pending[table_id] = (
                trigger,
                manual or (previous[1] if previous else False),
                pre_close or (previous[2] if previous else False),
                silent and (previous[3] if previous else True),
            )
            if table_id not in self._tasks:
                self._tasks[table_id] = asyncio.create_task(self._drain(table_id))

    async def wait_idle(self, table_id: str) -> None:
        task = self._tasks.get(table_id)
        if task is not None:
            await task

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._pending.clear()

    async def _drain(self, table_id: str) -> None:
        try:
            while True:
                async with self._lock:
                    trigger, manual, pre_close, silent = self._pending.pop(table_id, (None, False, False, False))
                await self._run(table_id, trigger=trigger, manual=manual, pre_close=pre_close, silent=silent)
                async with self._lock:
                    if table_id not in self._pending:
                        self._tasks.pop(table_id, None)
                        return
        except asyncio.CancelledError:
            async with self._lock:
                self._tasks.pop(table_id, None)
            raise

    async def _run(
        self,
        table_id: str,
        *,
        trigger: StageSummaryTrigger | None,
        manual: bool,
        pre_close: bool,
        silent: bool,
    ) -> None:
        state = self.repository.get(table_id)
        latest = self.repository.latest_stage_summary(table_id)
        context = build_agent_context(state, self.repository.turns(table_id), latest_summary=latest)
        decision = self.checkpoint_policy.evaluate(
            context.delta_turns,
            latest_summary=latest,
            semantic_trigger=trigger,
            manual_requested=manual,
            pre_close=pre_close,
        )
        # Quantity thresholds schedule review but do not publish a summary by themselves.
        if decision.trigger is None:
            return
        if not context.delta_turns:
            if not silent:
                await self._emit(table_id, {"type": "stage_summary_failed", "table_id": table_id, "input_state_version": state.version, "code": "no_uncovered_turns", "detail": "没有新的未总结发言"})
            return
        turn_id = context.delta_turns[-1].turn_id
        run_id = f"{table_id}:agent-run:{state.version}:{uuid4().hex[:8]}"
        claimed = await self.lease_store.claim(table_id, state.version)
        if not claimed:
            return
        started = self.clock()
        try:
            if not silent:
                await self._emit(table_id, {
                "type": "stage_summary_started",
                "table_id": table_id,
                "input_state_version": state.version,
                "trigger": decision.trigger,
                })
            try:
                specialist_outputs, specialist_meta = await asyncio.wait_for(
                    self._run_specialists(context), timeout=self.deadline_seconds
                )
            except asyncio.TimeoutError:
                specialist_outputs = {
                    "content_analyst": ContentAnalystAgent().fallback_factory(context),
                    "participation_analyst": ParticipationAnalystAgent().fallback_factory(context),
                }
                specialist_meta = {
                    "roles": ["content_analyst", "participation_analyst", "facilitation_strategist"],
                    "attempts": 1,
                    "used_fallback": True,
                }
            # Strategy remains a typed proposal; the existing deterministic
            # host loop is still the sole action/state writer for this phase.
            propose_action(context, specialist_outputs.get("content_analyst"), specialist_outputs.get("participation_analyst"))
            try:
                draft, draft_used_fallback = await asyncio.wait_for(
                    self._draft(context, decision.trigger), timeout=self.deadline_seconds
                )
            except asyncio.TimeoutError:
                draft = StageSummarizerAgent(trigger=decision.trigger).fallback_factory(context)
                draft_used_fallback = True
            verification = SummaryVerifierAgent().verify(draft, context)
            if verification.decision != "approved":
                if not silent:
                    await self._emit(table_id, {
                    "type": "stage_summary_failed",
                    "table_id": table_id,
                    "input_state_version": state.version,
                    "code": "verifier_rejected",
                    "detail": "总结未通过证据核验",
                    })
                await self._record_run(run_id, table_id, turn_id, state.version, "rejected", started, invoked_agents=specialist_meta["roles"] + ["stage_summarizer", "summary_verifier"], attempts=specialist_meta["attempts"], used_fallback=draft_used_fallback or specialist_meta["used_fallback"])
                return
            current = self.repository.get(table_id)
            if current.version != state.version:
                if not silent:
                    await self._emit(table_id, {
                    "type": "stage_summary_failed",
                    "table_id": table_id,
                    "input_state_version": state.version,
                    "code": "stale_state",
                    "detail": "桌面已经前进，旧总结已丢弃",
                    })
                await self._record_run(run_id, table_id, turn_id, state.version, "stale_discarded", started, invoked_agents=specialist_meta["roles"] + ["stage_summarizer", "summary_verifier"], attempts=specialist_meta["attempts"], used_fallback=specialist_meta["used_fallback"])
                return
            summary_id = uuid4().hex
            summary = StageSummary(
                **draft.model_dump(),
                summary_id=summary_id,
                table_id=table_id,
                revision=1,
                published_state_version=current.version + 1,
                created_at=self.clock(),
                model="deterministic-fallback" if draft_used_fallback else str(getattr(self.provider, "model", "custom")),
                used_fallback=draft_used_fallback or specialist_meta["used_fallback"],
            )
            next_state = current.model_copy(update={
                "version": current.version + 1,
                "latest_stage_summary_id": summary.summary_id,
                "latest_stage_summary_revision": summary.revision,
            })
            committed = self.repository.append_stage_summary_bundle(table_id, next_state, summary)
            if not silent:
                await self._emit(table_id, {
                "type": "stage_summary_published",
                "summary": summary.model_dump(mode="json"),
                })
            if not silent and self.broadcast_state is not None:
                await self.broadcast_state(table_id, committed)
            await self._record_run(run_id, table_id, turn_id, state.version, "summary_published", started, invoked_agents=specialist_meta["roles"] + ["stage_summarizer", "summary_verifier"], attempts=specialist_meta["attempts"], used_fallback=draft_used_fallback or specialist_meta["used_fallback"])
        except asyncio.TimeoutError:
            if not silent:
                await self._emit(table_id, {"type": "stage_summary_failed", "table_id": table_id, "input_state_version": state.version, "code": "deadline", "detail": "总结超过时间预算"})
            await self._record_run(run_id, table_id, turn_id, state.version, "timeout", started, error_code="deadline")
        except (ValueError, KeyError):
            if not silent:
                await self._emit(table_id, {"type": "stage_summary_failed", "table_id": table_id, "input_state_version": state.version, "code": "contract", "detail": "总结提交未通过合同校验"})
            await self._record_run(run_id, table_id, turn_id, state.version, "rejected", started, error_code="contract")
        finally:
            await self.lease_store.release(table_id, state.version)

    async def _run_specialists(self, context):
        roles = ["content_analyst", "participation_analyst", "facilitation_strategist"]
        if self.provider is None:
            content = ContentAnalystAgent().fallback_factory(context)
            participation = ParticipationAnalystAgent().fallback_factory(context)
            return {
                "content_analyst": content,
                "participation_analyst": participation,
            }, {"roles": roles, "attempts": 1, "used_fallback": True}
        content_call, participation_call = await asyncio.gather(
            ContentAnalystAgent().run(self.provider, context),
            ParticipationAnalystAgent().run(self.provider, context),
        )
        return {
            "content_analyst": content_call.value,
            "participation_analyst": participation_call.value,
        }, {
            "roles": roles,
            "attempts": max(content_call.attempts, participation_call.attempts),
            "used_fallback": content_call.used_fallback or participation_call.used_fallback,
        }

    async def _draft(self, context, trigger: StageSummaryTrigger):
        if self.provider is None:
            return StageSummarizerAgent(trigger=trigger).fallback_factory(context), True
        result = await StageSummarizerAgent(trigger=trigger).run(self.provider, context)
        return result.value, result.used_fallback

    async def _record_run(
        self,
        run_id: str,
        table_id: str,
        trigger_turn_id: int,
        input_state_version: int,
        outcome: str,
        started: float,
        *,
        error_code: str | None = None,
        invoked_agents: list[str] | None = None,
        attempts: int = 1,
        used_fallback: bool | None = None,
    ) -> None:
        effective_fallback = self.provider is None if used_fallback is None else used_fallback
        record = AgentRunRecord(
            run_id=run_id,
            table_id=table_id,
            trigger_turn_id=trigger_turn_id,
            input_state_version=input_state_version,
            outcome=outcome,
            invoked_agents=invoked_agents or ["stage_summarizer", "summary_verifier"],
            attempts=max(1, attempts),
            latency_ms=max(0, int((self.clock() - started) * 1000)),
            used_fallback=effective_fallback,
            error_code=error_code,
        )
        self.repository.append_agent_run(record)

    async def _emit(self, table_id: str, payload: dict) -> None:
        if self.broadcast is not None:
            await self.broadcast(table_id, payload)


__all__ = ("TableRunService",)
