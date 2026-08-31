"""Structured WebSocket stream for a conversation table."""

import asyncio
from collections import deque
import json
import math
import time
from collections.abc import Callable, Sequence
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, ValidationError

from app.domain import Action, AgentActionEvent, InvitationPreference, InterventionRecord, PeripheralComment, ReflectionResult, RouteDecision, SafetyLevel, TableState
from app.domain.schemas import EvidenceStatement
from app.orchestrator import (
    build_personal_card,
    build_shared_baseline,
    decide_intervention,
    enforce_safety,
    evaluate_reflection,
    evaluate_safety,
    generate_host_event_with_provider,
    record_intervention,
)
from app.providers import LLMProvider

from .nudge import NudgeCooldown, NudgeResult, NudgeUnavailable, run_nudge
from .intervention import build_intervention_record
from .privacy import project_state_for_viewer
from .repository import InMemoryTableRepository
from .identity import IdentityResolver, websocket_identity_error

DEFAULT_MAX_WEBSOCKET_FRAME_BYTES = 64 * 1024
DEFAULT_MAX_WEBSOCKET_EVENTS_PER_MINUTE = 120
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
    })
    return repository.update_intervention_record(table_id, updated)


async def _send_error(
    websocket: WebSocket,
    code: str,
    detail: str,
    *,
    retry_after_seconds: int | None = None,
) -> None:
    payload = {"type": "error", "code": code, "detail": detail}
    if retry_after_seconds is not None:
        payload["retry_after_seconds"] = retry_after_seconds
    await websocket.send_json(payload)


def register_websocket_routes(
    api: FastAPI,
    repository: InMemoryTableRepository,
    provider: LLMProvider | None = None,
    identity_resolver: IdentityResolver | None = None,
    websocket_allowed_origins: Sequence[str] | None = None,
    max_frame_bytes: int = DEFAULT_MAX_WEBSOCKET_FRAME_BYTES,
    max_events_per_minute: int = DEFAULT_MAX_WEBSOCKET_EVENTS_PER_MINUTE,
) -> None:
    """Register routes on a specific app instance so tests can inject a repository."""
    if max_frame_bytes <= 0:
        raise ValueError("max_frame_bytes must be a positive integer")
    if max_events_per_minute <= 0:
        raise ValueError("max_events_per_minute must be a positive integer")

    connections: dict[str, dict[WebSocket, str]] = {}
    table_locks: dict[str, asyncio.Lock] = {}

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

    async def broadcast(table_id: str, payload: dict) -> None:
        await _broadcast(table_id, lambda _viewer_id: payload)

    async def broadcast_state(table_id: str, state: TableState) -> None:
        await _broadcast(
            table_id,
            lambda viewer_id: _state_event(project_state_for_viewer(state, viewer_id or None)),
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
            state = repository.get(table_id)
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

                mutates_table = (
                    viewer_mode == "participant" and payload["type"] in {
                        "human_message", "participant_joined", "participant_left",
                        "participant_consent", "participant_invitation_preference",
                        "request_close", "request_nudge",
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
                        if safety.blocked:
                            state = repository.append_safety_state(
                                table_id, enforce_safety(repository.get(table_id), safety)
                            )
                            await _broadcast(
                                table_id,
                                lambda viewer_id: {
                                    "type": "safety_enforced",
                                    "decision": safety.model_dump(mode="json"),
                                    "state": project_state_for_viewer(
                                        state, viewer_id
                                    ).model_dump(mode="json"),
                                },
                            )
                            continue

                        state, created = repository.append_message_once(
                            table_id, participant_id, event.text, event.message_id
                        )
                        if not created:
                            await _send_error(
                                websocket,
                                "duplicate_message",
                                "message_id is already committed for this table",
                            )
                            continue
                        reflected = _reflect_latest_intervention(repository, table_id, state)
                        action = None
                        grounding_card = None
                        gate, route = decide_intervention(state)
                        if gate.should_speak and route.action is not Action.SILENCE:
                            grounding_card = (
                                repository.take_trusted_grounding_card(table_id)
                                if route.action is Action.GROUND else None
                            )
                            action = await generate_host_event_with_provider(
                                state, route, grounding_card, provider
                            )
                            agent_turn_id = f"{table_id}:agent:{state.version + 1}"
                            final_state = record_intervention(state, route, agent_turn_id)
                            action = action.model_copy(update={"state_version": final_state.version})
                            model_name = str(
                                getattr(provider, "model", None)
                                or (type(provider).__name__ if provider is not None else "deterministic-demo")
                            )
                            record = build_intervention_record(
                                table_id, final_state, route, action, model=model_name
                            )
                            state = repository.append_intervention_bundle(
                                table_id, final_state, record
                            )

                        await broadcast(table_id, {
                            "type": "message_committed",
                            "message": {
                                "message_id": event.message_id,
                                "participant_id": event.participant_id,
                                "text": event.text,
                                "client_ts": event.client_ts,
                            },
                        })
                        if action is not None:
                            await broadcast(table_id, {
                                "type": "agent_action",
                                **action.model_dump(mode="json"),
                                "gate": gate.model_dump(mode="json"),
                                "route": route.model_dump(mode="json"),
                            })
                        if action is not None and action.action is Action.GROUND and grounding_card is not None:
                            await broadcast(table_id, {
                                "type": "grounding_card",
                                "table_id": table_id,
                                "state_version": state.version,
                                **grounding_card.model_dump(mode="json"),
                            })
                        await broadcast_state(table_id, state)
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
                            state = repository.close_table(table_id)
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
