"""Minimal structured WebSocket stream for a single conversation table."""

from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, ValidationError

from app.domain import Action, HumanTurn, TableState
from app.orchestrator import decide_intervention, generate_host_event, record_intervention

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


class _RequestDebugState(_ClientEvent):
    type: Literal["request_debug_state"]


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
                    turn = HumanTurn(
                        turn_id=max((item.turn_id for item in repository.turns(table_id)), default=0) + 1,
                        participant_id=participant_id,
                        text=event.text,
                    )
                    state = repository.append_turn(table_id, turn)
                    action = None
                    gate, route = decide_intervention(state)
                    if gate.should_speak:
                        if route.action is not Action.SILENCE:
                            action = generate_host_event(state, route)
                            agent_turn_id = f"{table_id}:agent:{state.version + 1}"
                            final_state = record_intervention(state, route, agent_turn_id)
                            state = repository.append_intervention_state(table_id, final_state)
                            action = action.model_copy(update={"state_version": state.version})
                    await websocket.send_json(
                        {
                            "type": "message_committed",
                            "message": {
                                "message_id": event.message_id,
                                "participant_id": event.participant_id,
                                "text": event.text,
                                "client_ts": event.client_ts,
                            },
                        }
                    )
                    if action is not None:
                        await websocket.send_json(
                            {
                                "type": "agent_action",
                                **action.model_dump(mode="json"),
                                "gate": gate.model_dump(mode="json"),
                                "route": route.model_dump(mode="json"),
                            }
                        )
                    await websocket.send_json(_state_event(state))
                elif payload["type"] == "participant_joined":
                    event = _ParticipantJoined.model_validate(payload)
                    if event.participant_id != participant_id:
                        raise ValueError("participant_id must match the WebSocket query")
                    state = repository.get(table_id)
                    if event.participant_id not in state.participants:
                        raise ValueError(f"unknown participant: {event.participant_id}")
                    await websocket.send_json(_state_event(state))
                elif payload["type"] == "participant_left":
                    event = _ParticipantLeft.model_validate(payload)
                    if event.participant_id != participant_id:
                        raise ValueError("participant_id must match the WebSocket query")
                    await websocket.send_json(_state_event(repository.remove_participant(table_id, event.participant_id)))
                elif payload["type"] == "request_debug_state":
                    _RequestDebugState.model_validate(payload)
                    await websocket.send_json(_state_event(repository.get(table_id)))
                else:
                    await _send_error(websocket, "unknown_event", f"unsupported event type: {payload['type']}")
            except ValidationError:
                await _send_error(websocket, "invalid_payload", "event payload does not match its contract")
            except (KeyError, ValueError) as error:
                await _send_error(websocket, "invalid_event", str(error))


__all__ = ("register_websocket_routes",)
