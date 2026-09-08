"""Structured WebSocket stream for a conversation table."""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
import json
import math
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, ValidationError

from app.domain import Action, AgentActionEvent, InvitationPreference, InterventionRecord, PeripheralComment, ReflectionResult, RouteDecision, SafetyLevel, TableState
from app.domain.schemas import EvidenceStatement
from app.orchestrator import (
    build_personal_card,
    build_shared_baseline,
    decide_intervention,
    enforce_safety,
    escalate_boundary_safety,
    evaluate_reflection,
    evaluate_safety,
    generate_host_event_with_provider,
    record_intervention,
)
from app.providers import LLMProvider

from .nudge import NudgeCooldown, NudgeResult, NudgeUnavailable, run_nudge
from .intervention import build_intervention_record
from .privacy import project_state_for_viewer
from .repository import MAX_SAFETY_STRIKES_PER_PARTICIPANT, InMemoryTableRepository
from .identity import IdentityResolver, websocket_identity_error
from .event_bus import EventBus

DEFAULT_MAX_WEBSOCKET_FRAME_BYTES = 64 * 1024
DEFAULT_MAX_WEBSOCKET_EVENTS_PER_MINUTE = 120


class _MonotonicStateBroadcast:
    """Serialize state fanout and suppress projections older than the last send."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_versions: dict[str, int] = {}

    async def send(
        self,
        table_id: str,
        state_version: int,
        callback: Callable[[], Awaitable[None]],
    ) -> bool:
        lock = self._locks.setdefault(table_id, asyncio.Lock())
        async with lock:
            previous = self._last_versions.get(table_id)
            if previous is not None and state_version < previous:
                return False
            self._last_versions[table_id] = state_version
            await callback()
            return True
WEBSOCKET_EVENT_WINDOW_SECONDS = 60.0


class _FrameTooLarge(ValueError):
    """Raised before JSON parsing when a client frame exceeds the protocol bound."""


class _RateLimited(ValueError):
    """Raised before JSON parsing when one connection exceeds its event budget."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("websocket event rate limit exceeded")


class _ConnectionEventRateLimiter:
    """Sliding-window limiter isolated to one WebSocket connection."""

    def __init__(self, max_events_per_minute: int) -> None:
        self.max_events_per_minute = max_events_per_minute
        self._timestamps: deque[float] = deque()

    def consume(self) -> None:
        now = time.monotonic()
        cutoff = now - WEBSOCKET_EVENT_WINDOW_SECONDS
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_events_per_minute:
            retry_after = max(
                1,
                math.ceil(self._timestamps[0] + WEBSOCKET_EVENT_WINDOW_SECONDS - now),
            )
            raise _RateLimited(retry_after)
        self._timestamps.append(now)


async def _receive_json_bounded(
    websocket: WebSocket,
    max_frame_bytes: int,
    rate_limiter: _ConnectionEventRateLimiter | None = None,
) -> object:
    """Receive one text JSON frame without parsing an oversized payload."""
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000), message.get("reason"))
    text = message.get("text")
    if text is None:
        raise ValueError("event must be a text JSON frame")
    if len(text.encode("utf-8")) > max_frame_bytes:
        raise _FrameTooLarge
    if rate_limiter is not None:
        rate_limiter.consume()
    return json.loads(text)


class _ClientEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str


class _HumanMessage(_ClientEvent):
    type: Literal["human_message"]
    message_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)
    client_ts: JsonValue
    turn_id: PositiveInt | None = None


class _ParticipantJoined(_ClientEvent):
    type: Literal["participant_joined"]
    participant_id: str = Field(min_length=1)


class _ParticipantLeft(_ClientEvent):
    type: Literal["participant_left"]
    participant_id: str = Field(min_length=1)


class _ParticipantConsent(_ClientEvent):
    type: Literal["participant_consent"]
    participant_id: str = Field(min_length=1)
    profile_shared: bool


class _ParticipantInvitationPreference(_ClientEvent):
    type: Literal["participant_invitation_preference"]
    participant_id: str = Field(min_length=1)
    preference: InvitationPreference


class _RequestDebugState(_ClientEvent):
    type: Literal["request_debug_state"]


class _RequestClose(_ClientEvent):
    type: Literal["request_close"]


class _RequestNudge(_ClientEvent):
    type: Literal["request_nudge"]


class _RequestStageSummary(_ClientEvent):
    type: Literal["request_stage_summary"]
    request_id: str | None = Field(default=None, min_length=1, max_length=120)


class _PeripheralComment(_ClientEvent):
    type: Literal["peripheral_comment"]
    comment_id: str = Field(min_length=1)
    author_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=500)


def _state_event(state: TableState) -> dict:
    return {
        "type": "table_state_changed",
        "phase": state.phase.value,
        "momentum": state.momentum.value,
        "close_readiness": state.close_readiness.value,
        "state": state.model_dump(mode="json"),
    }


def _reflect_latest_intervention(repository, table_id: str, state: TableState) -> InterventionRecord | None:
    """Attach post-intervention evidence after two human turns, once only."""
    records = repository.interventions(table_id)
    if not records:
        return None
    record = records[-1]
    if record.reflection is not None or state.intervention.human_turns_since_last_intervention < 2:
        return None
    before_version = record.state_version - 1
    before = next((item for item in repository.replay(table_id) if item.version == before_version), None)
    if before is None:
        return None
    route = RouteDecision(
        action=record.action,
        target_participant_id=record.target_participant_id,
        evidence_turns=record.evidence_turns,
        confidence=record.confidence,
    )
    reflection: ReflectionResult = evaluate_reflection(
        before, state, route,
        human_turn_ids=[turn.turn_id for turn in repository.turns(table_id)
                        if turn.turn_id > max(record.evidence_turns, default=0)],
    )
    evidence_items = [*reflection.effects, *reflection.negative_effects]
    evidence = sorted({turn_id for item in evidence_items for turn_id in item.evidence_turns})
    if not evidence:
        return None
    outcome_text = "；".join(item.text for item in evidence_items)
    updated = record.model_copy(update={
        "outcome": EvidenceStatement(text=outcome_text, evidence_turns=evidence),
        "reflection": EvidenceStatement(text=reflection.strategy_note, evidence_turns=evidence),
        "reflection_effective": reflection.effective,
    })
    return repository.update_intervention_record(table_id, updated)


async def _send_error(
    websocket: WebSocket,
    code: str,
    detail: str,
    *,
    retry_after_seconds: int | None = None,
    message_id: str | None = None,
) -> None:
    payload = {"type": "error", "code": code, "detail": detail}
    if retry_after_seconds is not None:
        payload["retry_after_seconds"] = retry_after_seconds
    if message_id is not None:
        payload["message_id"] = message_id
    await websocket.send_json(payload)


def register_websocket_routes(
    api: FastAPI,
    repository: InMemoryTableRepository,
    provider: LLMProvider | None = None,
    identity_resolver: IdentityResolver | None = None,
    websocket_allowed_origins: Sequence[str] | None = None,
    max_frame_bytes: int = DEFAULT_MAX_WEBSOCKET_FRAME_BYTES,
    max_events_per_minute: int = DEFAULT_MAX_WEBSOCKET_EVENTS_PER_MINUTE,
    clock: Callable[[], float] = time.time,
    event_bus: EventBus | None = None,
) -> None:
    """Register routes on a specific app instance so tests can inject a repository."""
    if max_frame_bytes <= 0:
        raise ValueError("max_frame_bytes must be a positive integer")
    if max_events_per_minute <= 0:
        raise ValueError("max_events_per_minute must be a positive integer")

    connections: dict[str, dict[WebSocket, str]] = {}
    table_locks: dict[str, asyncio.Lock] = {}
    state_broadcast = _MonotonicStateBroadcast()
    host_tasks: set[asyncio.Task[None]] = set()
    instance_id = uuid4().hex
    bus_task: asyncio.Task[None] | None = None

    async def _publish_bus(
        table_id: str,
        *,
        kind: Literal["event", "state", "safety"],
        payload: dict,
        state_version: int | None = None,
    ) -> None:
        """Publish only public event metadata; local fanout never depends on it."""
        if event_bus is None:
            return
        envelope = {
            "origin": instance_id,
            "kind": kind,
            "table_id": table_id,
            "state_version": state_version,
            "payload": payload,
        }
        try:
            await asyncio.to_thread(
                event_bus.publish,
                channel=f"table:{table_id}",
                payload=envelope,
            )
        except Exception:
            # The shared bus is an optional cross-worker enhancement.  A local
            # connection must remain usable if its coordination store is down.
            return

    async def _broadcast(table_id: str, factory: Callable[[str], dict]) -> None:
        """Fan out public table events and discard peers that already closed."""
        peers = tuple(connections.get(table_id, {}).items())
        stale: list[WebSocket] = []
        for peer, viewer_id in peers:
            try:
                await peer.send_json(factory(viewer_id))
            except (OSError, RuntimeError, WebSocketDisconnect):
                stale.append(peer)
        if stale:
            current = connections.get(table_id)
            if current is not None:
                for peer in stale:
                    current.pop(peer, None)
                if not current:
                    connections.pop(table_id, None)

    async def _broadcast_state_local(table_id: str, state: TableState) -> None:
        await state_broadcast.send(
            table_id,
            state.version,
            lambda: _broadcast(
                table_id,
                lambda viewer_id: _state_event(
                    project_state_for_viewer(state, viewer_id or None)
                ),
            ),
        )

    async def broadcast(table_id: str, payload: dict) -> None:
        await _broadcast(table_id, lambda _viewer_id: payload)
        await _publish_bus(table_id, kind="event", payload=payload)

    async def broadcast_state(table_id: str, state: TableState) -> None:
        sent = await state_broadcast.send(
            table_id,
            state.version,
            lambda: _broadcast(
                table_id,
                lambda viewer_id: _state_event(
                    project_state_for_viewer(state, viewer_id or None)
                ),
            ),
        )
        if sent:
            await _publish_bus(
                table_id,
                kind="state",
                state_version=state.version,
                payload={"type": "table_state_changed"},
            )

    async def broadcast_safety(table_id: str, decision, state: TableState) -> None:
        await _broadcast(
            table_id,
            lambda viewer_id: {
                "type": "safety_enforced",
                "decision": decision.model_dump(mode="json"),
                "state": project_state_for_viewer(state, viewer_id or None).model_dump(mode="json"),
            },
        )
        await _publish_bus(
            table_id,
            kind="safety",
            state_version=state.version,
            payload={
                "type": "safety_enforced",
                "decision": decision.model_dump(mode="json"),
            },
        )

    def schedule_host_intervention(
        table_id: str,
        state: TableState,
        gate,
        route,
        grounding_card,
    ) -> None:
        """Run the optional host model after the human turn is visible.

        The human commit and its state snapshot are already broadcast before
        this task starts.  If another turn wins the race while the provider is
        running, the stale intervention is discarded rather than blocking or
        rewriting the newer table state.
        """
        async def run() -> None:
            try:
                action = await generate_host_event_with_provider(
                    state, route, grounding_card, provider
                )
                current = repository.get(table_id)
                if current.version != state.version:
                    return
                agent_turn_id = f"{table_id}:agent:{current.version + 1}"
                final_state = record_intervention(current, route, agent_turn_id)
                action = action.model_copy(update={"state_version": final_state.version})
                model_name = str(
                    getattr(provider, "model", None)
                    or (type(provider).__name__ if provider is not None else "deterministic-demo")
                )
                record = build_intervention_record(
                    table_id,
                    final_state,
                    route,
                    action,
                    model=model_name,
                    grounding_card=grounding_card,
                )
                committed = repository.append_intervention_bundle(
                    table_id,
                    final_state,
                    record,
                    consume_grounding_card=route.action is Action.GROUND
                    and grounding_card is not None,
                )
                await broadcast(table_id, {
                    "type": "agent_action",
                    **action.model_dump(mode="json"),
                    "gate": gate.model_dump(mode="json"),
                    "route": route.model_dump(mode="json"),
                })
                if action.action is Action.GROUND and grounding_card is not None:
                    await broadcast(table_id, {
                        "type": "grounding_card",
                        "table_id": table_id,
                        "state_version": committed.version,
                        **grounding_card.model_dump(mode="json"),
                    })
                await broadcast_state(table_id, committed)
            except (KeyError, ValueError, RuntimeError):
                # A close, safety pause, or competing writer can invalidate a
                # queued intervention. The committed human turn remains valid.
                return

        task = asyncio.create_task(run())
        host_tasks.add(task)
        task.add_done_callback(host_tasks.discard)

    async def _poll_shared_bus() -> None:
        """Forward events written by other workers to this worker's sockets."""
        if event_bus is None:
            return
        cursor = 0
        latest_id = getattr(event_bus, "latest_id", None)
        if latest_id is not None:
            try:
                cursor = int(await asyncio.to_thread(latest_id))
            except Exception:
                cursor = 0
        while True:
            try:
                events = await asyncio.to_thread(
                    event_bus.read_since, cursor=cursor, limit=100
                )
                if events:
                    for item in events:
                        cursor = max(cursor, item.event_id)
                        payload = item.payload
                        if payload.get("origin") == instance_id:
                            continue
                        table_id = payload.get("table_id")
                        if not isinstance(table_id, str) or not table_id:
                            continue
                        kind = payload.get("kind")
                        if kind == "event":
                            event_payload = payload.get("payload")
                            if isinstance(event_payload, dict):
                                await _broadcast(
                                    table_id,
                                    lambda _viewer_id, event_payload=event_payload: event_payload,
                                )
                        elif kind == "state":
                            try:
                                state = repository.get(table_id)
                            except KeyError:
                                continue
                            version = payload.get("state_version")
                            if isinstance(version, int) and state.version < version:
                                continue
                            await _broadcast_state_local(table_id, state)
                        elif kind == "safety":
                            try:
                                state = repository.get(table_id)
                            except KeyError:
                                continue
                            event_payload = payload.get("payload")
                            if not isinstance(event_payload, dict):
                                continue
                            decision = event_payload.get("decision")
                            if not isinstance(decision, dict):
                                continue
                            await _broadcast(
                                table_id,
                                lambda viewer_id, event_payload=event_payload, state=state: {
                                    **event_payload,
                                    "state": project_state_for_viewer(
                                        state, viewer_id or None
                                    ).model_dump(mode="json"),
                                },
                            )
                else:
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.25)

    if event_bus is not None:
        previous_lifespan = api.router.lifespan_context

        @asynccontextmanager
        async def _shared_bus_lifespan(application: FastAPI):
            nonlocal bus_task
            async with previous_lifespan(application):
                bus_task = asyncio.create_task(_poll_shared_bus())
                try:
                    yield
                finally:
                    if bus_task is not None:
                        bus_task.cancel()
                        try:
                            await bus_task
                        except asyncio.CancelledError:
                            pass
                        bus_task = None

        api.router.lifespan_context = _shared_bus_lifespan

    # REST routes can reuse the same table-scoped fanout without reaching into
    # the connection registry or duplicating privacy projection logic.
    api.state.table_broadcast = broadcast
    api.state.table_broadcast_state = broadcast_state
    api.state.table_broadcast_safety = broadcast_safety

    @api.websocket("/ws/tables/{table_id}")
    async def table_events(
        websocket: WebSocket,
        table_id: str,
        participant_id: str = "",
        viewer_mode: Literal["participant", "observer", "commenter"] = "participant",
    ) -> None:
        if websocket_allowed_origins is not None:
            origin = websocket.headers.get("origin")
            if origin not in websocket_allowed_origins:
                await websocket.close(code=1008)
                return
        await websocket.accept()
        if not participant_id.strip():
            await _send_error(websocket, "invalid_participant", "participant_id is required")
            await websocket.close(code=1008)
            return
        identity_error = websocket_identity_error(
            identity_resolver, websocket, participant_id
        )
        if identity_error is not None:
            detail = (
                "authenticated subject does not match participant_id"
                if identity_error == "identity_mismatch"
                else "authentication required"
            )
            await _send_error(websocket, identity_error, detail)
            await websocket.close(code=1008)
            return
        try:
            state, _expired = repository.expire_sync_if_due(table_id, now=clock())
        except KeyError:
            await _send_error(websocket, "unknown_table", f"unknown table: {table_id}")
            await websocket.close(code=1008)
            return
        if viewer_mode == "participant" and participant_id not in state.participants:
            await _send_error(websocket, "unknown_participant", f"unknown participant: {participant_id}")
            await websocket.close(code=1008)
            return

        connection_viewer_id = participant_id if viewer_mode == "participant" else ""
        connections.setdefault(table_id, {})[websocket] = connection_viewer_id
        rate_limiter = _ConnectionEventRateLimiter(max_events_per_minute)
        if viewer_mode in {"observer", "commenter"}:
            await websocket.send_json(_state_event(project_state_for_viewer(state, None)))
        table_lock = table_locks.setdefault(table_id, asyncio.Lock())
        try:
            while True:
                try:
                    payload = await _receive_json_bounded(
                        websocket, max_frame_bytes, rate_limiter
                    )
                except WebSocketDisconnect:
                    return
                except _FrameTooLarge:
                    await websocket.close(code=1009)
                    return
                except _RateLimited as error:
                    await _send_error(
                        websocket,
                        "rate_limited",
                        "too many WebSocket events; retry later",
                        retry_after_seconds=error.retry_after_seconds,
                    )
                    continue
                except (TypeError, ValueError):
                    await _send_error(websocket, "invalid_event", "event must be a JSON object")
                    continue

                if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
                    await _send_error(websocket, "invalid_event", "event must include a string type")
                    continue

                state, sync_expired = repository.expire_sync_if_due(
                    table_id, now=clock()
                )
                if sync_expired:
                    await broadcast(table_id, {
                        "type": "table_mode_changed",
                        "mode": state.conversation.mode.value,
                        "reason": "sync_window_expired",
                        "state_version": state.version,
                    })
                    await broadcast_state(table_id, state)

                mutates_table = (
                    viewer_mode == "participant" and payload["type"] in {
                        "human_message", "participant_joined", "participant_left",
                        "participant_consent", "participant_invitation_preference",
                        "request_close", "request_nudge", "request_stage_summary",
                    }
                ) or (
                    viewer_mode == "commenter" and payload["type"] == "peripheral_comment"
                )
                if mutates_table:
                    await table_lock.acquire()
                try:
                    if viewer_mode == "observer" and payload["type"] != "request_debug_state":
                        await _send_error(
                            websocket,
                            "observer_read_only",
                            "observer connections cannot mutate the table",
                        )
                        continue
                    if viewer_mode == "commenter" and payload["type"] not in {
                        "peripheral_comment", "request_debug_state",
                    }:
                        await _send_error(
                            websocket,
                            "commenter_read_only",
                            "commenter connections can only submit peripheral comments",
                        )
                        continue
                    if payload["type"] == "peripheral_comment":
                        event = _PeripheralComment.model_validate(payload)
                        if viewer_mode != "commenter":
                            await _send_error(
                                websocket,
                                "commenter_only",
                                "peripheral comments require commenter mode",
                            )
                            continue
                        if event.author_id != participant_id:
                            raise ValueError("author_id must match the WebSocket query")
                        current_state = repository.get(table_id)
                        if current_state.conversation.closed:
                            await _send_error(websocket, "table_closed", "table is already closed")
                            continue
                        if current_state.conversation.soft_expired:
                            await _send_error(websocket, "table_soft_expired", "table is soft-expired")
                            continue
                        comment, created = repository.append_comment_once(PeripheralComment(
                            comment_id=event.comment_id,
                            table_id=table_id,
                            author_id=event.author_id,
                            display_name=event.display_name,
                            text=event.text,
                            state_version=current_state.version,
                        ))
                        if not created:
                            await _send_error(
                                websocket,
                                "duplicate_comment",
                                "comment_id is already committed for this table",
                            )
                            continue
                        await broadcast(table_id, {
                            "type": "peripheral_comment",
                            "comment": comment.model_dump(mode="json"),
                        })
                        continue
                    if payload["type"] == "human_message":
                        event = _HumanMessage.model_validate(payload)
                        if event.participant_id != participant_id:
                            raise ValueError("participant_id must match the WebSocket query")
                        current_state = repository.get(table_id)
                        # A participant can leave while an existing socket is still
                        # connected.  Re-check membership before safety handling so
                        # a stale connection cannot create a safety snapshot or turn.
                        if event.participant_id not in current_state.participants:
                            raise ValueError(f"unknown participant: {event.participant_id}")
                        if current_state.conversation.closed:
                            await _send_error(websocket, "table_closed", "table is already closed")
                            continue
                        if current_state.conversation.soft_expired:
                            await _send_error(websocket, "table_soft_expired", "table is soft-expired")
                            continue
                        if current_state.conversation.safety_level is SafetyLevel.CRITICAL:
                            await _send_error(websocket, "table_paused", "table is paused for safety review")
                            continue
                        # The id is only needed to annotate a possible safety
                        # decision here.  A safe message receives its authoritative
                        # turn id inside the repository's atomic commit below.
                        turn_id = max((item.turn_id for item in repository.turns(table_id)), default=0) + 1
                        safety = evaluate_safety(event.text, turn_id)
                        if safety.blocked and safety.level is SafetyLevel.ELEVATED:
                            strike_count = repository.record_safety_strike(
                                table_id, participant_id
                            )
                            if strike_count < MAX_SAFETY_STRIKES_PER_PARTICIPANT:
                                await websocket.send_json({
                                    "type": "safety_private_reminder",
                                    "participant_id": participant_id,
                                    "strike_count": strike_count,
                                    "text": "先停一下，我们把观点和人分开，再继续这桌讨论。",
                                })
                                continue
                            safety = escalate_boundary_safety(safety, turn_id)
                        if safety.blocked:
                            state = repository.append_safety_state(
                                table_id, enforce_safety(repository.get(table_id), safety)
                            )
                            await broadcast_safety(table_id, safety, state)
                            continue

                        state, created = repository.append_message_once(
                            table_id, participant_id, event.text, event.message_id
                        )
                        if not created:
                            await _send_error(
                                websocket,
                                "duplicate_message",
                                "message_id is already committed for this table",
                                message_id=event.message_id,
                            )
                            continue
                        # Commit and fan out the human turn before any provider
                        # call. The table stays responsive while Host thinks.
                        await broadcast(table_id, {
                            "type": "message_committed",
                            "message": {
                                "message_id": event.message_id,
                                "participant_id": event.participant_id,
                                "text": event.text,
                                "client_ts": event.client_ts,
                            },
                        })
                        await broadcast_state(table_id, state)
                        reflected = _reflect_latest_intervention(repository, table_id, state)
                        gate, route = decide_intervention(state)
                        if gate.should_speak and route.action is not Action.SILENCE:
                            grounding_card = (
                                repository.peek_trusted_grounding_card(table_id)
                                if route.action is Action.GROUND else None
                            )
                            schedule_host_intervention(table_id, state, gate, route, grounding_card)
                        if safety.level is SafetyLevel.ELEVATED:
                            await broadcast(table_id, {
                                "type": "safety_soft_intervention",
                                "text": "我们先把观点和人分开，回到具体经历。",
                                "state_version": state.version,
                            })
                        if reflected is not None:
                            await broadcast(table_id, {
                                "type": "intervention_reflected",
                                "record": reflected.model_dump(mode="json"),
                            })
                    elif payload["type"] == "request_nudge":
                        _RequestNudge.model_validate(payload)
                        try:
                            result: NudgeResult = await run_nudge(
                                repository, table_id, participant_id, provider
                            )
                        except PermissionError as error:
                            raise ValueError(str(error)) from error
                        except NudgeUnavailable as error:
                            code = (
                                "table_closed" if str(error) == "table is already closed"
                                else "table_soft_expired" if str(error) == "table is soft-expired"
                                else "table_paused" if str(error) == "table is paused for safety review"
                                else "nudge_unavailable"
                            )
                            await _send_error(websocket, code, str(error))
                            continue
                        except NudgeCooldown as error:
                            await _send_error(websocket, "intervention_cooldown", str(error))
                            continue
                        gate, route, action, state = (
                            result.gate, result.route, result.action, result.state
                        )
                        await broadcast(table_id, {
                            "type": "agent_action",
                            **action.model_dump(mode="json"),
                            "gate": gate.model_dump(mode="json"),
                            "route": route.model_dump(mode="json"),
                        })
                        await broadcast_state(table_id, state)
                    elif payload["type"] == "request_stage_summary":
                        event = _RequestStageSummary.model_validate(payload)
                        state = repository.get(table_id)
                        if participant_id not in state.participants:
                            raise ValueError(f"unknown participant: {participant_id}")
                        if state.conversation.closed or state.conversation.soft_expired:
                            await _send_error(websocket, "table_not_active", "table is not active")
                            continue
                        if state.conversation.safety_level is SafetyLevel.CRITICAL:
                            await _send_error(websocket, "table_paused", "table is paused for safety review")
                            continue
                        if not repository.turns(table_id):
                            await _send_error(websocket, "summary_unavailable", "summary requires a committed turn")
                            continue
                        service = getattr(api.state, "table_run_service", None)
                        if service is None:
                            await _send_error(websocket, "summary_unavailable", "summary service is unavailable")
                            continue
                        await service.enqueue(table_id, manual=True)
                        await websocket.send_json({
                            "type": "stage_summary_requested",
                            "table_id": table_id,
                            "state_version": state.version,
                            **({"request_id": event.request_id} if event.request_id else {}),
                        })
                    elif payload["type"] == "participant_joined":
                        event = _ParticipantJoined.model_validate(payload)
                        if event.participant_id != participant_id:
                            raise ValueError("participant_id must match the WebSocket query")
                        state = repository.get(table_id)
                        if event.participant_id not in state.participants:
                            raise ValueError(f"unknown participant: {event.participant_id}")
                        await broadcast_state(table_id, state)
                    elif payload["type"] == "participant_left":
                        event = _ParticipantLeft.model_validate(payload)
                        if event.participant_id != participant_id:
                            raise ValueError("participant_id must match the WebSocket query")
                        state = repository.remove_participant(table_id, event.participant_id)
                        await broadcast_state(table_id, state)
                    elif payload["type"] == "participant_consent":
                        event = _ParticipantConsent.model_validate(payload)
                        if event.participant_id != participant_id:
                            raise ValueError("participant_id must match the WebSocket query")
                        state = repository.set_profile_consent(
                            table_id, participant_id, event.profile_shared
                        )
                        await broadcast(table_id, {
                            "type": "participant_consent_changed",
                            "participant_id": participant_id,
                            "profile_shared": event.profile_shared,
                        })
                        await broadcast_state(table_id, state)
                    elif payload["type"] == "participant_invitation_preference":
                        event = _ParticipantInvitationPreference.model_validate(payload)
                        if event.participant_id != participant_id:
                            raise ValueError("participant_id must match the WebSocket query")
                        previous_state = repository.get(table_id)
                        state = repository.set_invitation_preference(
                            table_id, participant_id, event.preference
                        )
                        if state.version != previous_state.version:
                            await broadcast(table_id, {
                                "type": "participant_invitation_preference_changed",
                                "participant_id": participant_id,
                                "preference": event.preference.value,
                                "state_version": state.version,
                            })
                            await broadcast_state(table_id, state)
                    elif payload["type"] == "request_debug_state":
                        _RequestDebugState.model_validate(payload)
                        await websocket.send_json(_state_event(
                            project_state_for_viewer(
                                repository.get(table_id),
                                participant_id if viewer_mode == "participant" else None,
                            )
                        ))
                    elif payload["type"] == "request_close":
                        _RequestClose.model_validate(payload)
                        state = repository.get(table_id)
                        if participant_id not in state.participants:
                            raise ValueError(f"unknown participant: {participant_id}")
                        await broadcast(table_id, {
                            "type": "close_started",
                            "table_id": table_id,
                            "state_version": state.version,
                            "reason": "participant_requested_close",
                        })
                        try:
                            build_shared_baseline(state, turns=repository.turns(table_id))
                            state = repository.close_table_for_participant(table_id, participant_id)
                            baseline = build_shared_baseline(state, turns=repository.turns(table_id))
                            personal_card = build_personal_card(state, participant_id)
                        except ValueError as error:
                            await _send_error(websocket, "close_artifact_unavailable", str(error))
                            continue
                        await websocket.send_json({
                            "type": "close_artifact_ready",
                            "table_id": table_id,
                            "state_version": state.version,
                            "shared_baseline": baseline.model_dump(mode="json"),
                            "personal_card": personal_card.model_dump(mode="json"),
                        })
                        await broadcast_state(table_id, state)
                    else:
                        await _send_error(websocket, "unknown_event", f"unsupported event type: {payload['type']}")
                except ValidationError:
                    await _send_error(websocket, "invalid_payload", "event payload does not match its contract")
                except (KeyError, ValueError) as error:
                    await _send_error(websocket, "invalid_event", str(error))
                finally:
                    if mutates_table:
                        table_lock.release()
        finally:
            peers = connections.get(table_id)
            if peers is not None:
                peers.pop(websocket, None)
                if not peers:
                    connections.pop(table_id, None)
                    table_locks.pop(table_id, None)


__all__ = ("register_websocket_routes",)
