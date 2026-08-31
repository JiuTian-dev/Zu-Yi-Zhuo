"""Structured WebSocket stream for a conversation table."""

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, ValidationError

from app.domain import Action, HumanTurn, SafetyLevel, TableState
from app.orchestrator import (
    build_personal_card,
    build_shared_baseline,
    decide_intervention,
    enforce_safety,
    evaluate_safety,
    generate_host_event,
    record_intervention,
)

from .privacy import project_state_for_viewer
from .repository import InMemoryTableRepository


class _ClientEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str


class _HumanMessage(_ClientEvent):
    type: Literal["human_message"]
    message_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
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


class _RequestDebugState(_ClientEvent):
    type: Literal["request_debug_state"]


class _RequestClose(_ClientEvent):
    type: Literal["request_close"]


def _state_event(state: TableState) -> dict:
    return {
        "type": "table_state_changed",
        "phase": state.phase.value,
        "momentum": state.momentum.value,
        "close_readiness": state.close_readiness.value,
        "state": state.model_dump(mode="json"),
    }


async def _send_error(websocket: WebSocket, code: str, detail: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "detail": detail})


def register_websocket_routes(api: FastAPI, repository: InMemoryTableRepository) -> None:
    """Register routes on a specific app instance so tests can inject a repository."""

    connections: dict[str, dict[WebSocket, str]] = {}

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
            lambda viewer_id: _state_event(project_state_for_viewer(state, viewer_id)),
        )

    @api.websocket("/ws/tables/{table_id}")
    async def table_events(websocket: WebSocket, table_id: str, participant_id: str = "") -> None:
        await websocket.accept()
        if not participant_id.strip():
            await _send_error(websocket, "invalid_participant", "participant_id is required")
            await websocket.close(code=1008)
            return
        try:
            repository.get(table_id)
        except KeyError:
            await _send_error(websocket, "unknown_table", f"unknown table: {table_id}")
            await websocket.close(code=1008)
            return

        connections.setdefault(table_id, {})[websocket] = participant_id
        try:
            while True:
                try:
                    payload = await websocket.receive_json()
                except WebSocketDisconnect:
                    return
                except (TypeError, ValueError):
                    await _send_error(websocket, "invalid_event", "event must be a JSON object")
                    continue

                if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
                    await _send_error(websocket, "invalid_event", "event must include a string type")
                    continue

                try:
                    if payload["type"] == "human_message":
                        event = _HumanMessage.model_validate(payload)
                        if event.participant_id != participant_id:
                            raise ValueError("participant_id must match the WebSocket query")
                        if repository.get(table_id).conversation.safety_level is SafetyLevel.CRITICAL:
                            await _send_error(websocket, "table_paused", "table is paused for safety review")
                            continue
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

                        turn = HumanTurn(turn_id=turn_id, participant_id=participant_id, text=event.text)
                        state = repository.append_turn(table_id, turn)
                        action = None
                        grounding_card = None
                        gate, route = decide_intervention(state)
                        if gate.should_speak and route.action is not Action.SILENCE:
                            grounding_card = (
                                repository.take_trusted_grounding_card(table_id)
                                if route.action is Action.GROUND else None
                            )
                            action = generate_host_event(state, route, grounding_card)
                            agent_turn_id = f"{table_id}:agent:{state.version + 1}"
                            final_state = record_intervention(state, route, agent_turn_id)
                            state = repository.append_intervention_state(table_id, final_state)
                            action = action.model_copy(update={"state_version": state.version})

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
                    elif payload["type"] == "request_debug_state":
                        _RequestDebugState.model_validate(payload)
                        await websocket.send_json(_state_event(
                            project_state_for_viewer(repository.get(table_id), participant_id)
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
                    else:
                        await _send_error(websocket, "unknown_event", f"unsupported event type: {payload['type']}")
                except ValidationError:
                    await _send_error(websocket, "invalid_payload", "event payload does not match its contract")
                except (KeyError, ValueError) as error:
                    await _send_error(websocket, "invalid_event", str(error))
        finally:
            peers = connections.get(table_id)
            if peers is not None:
                peers.pop(websocket, None)
                if not peers:
                    connections.pop(table_id, None)


__all__ = ("register_websocket_routes",)
