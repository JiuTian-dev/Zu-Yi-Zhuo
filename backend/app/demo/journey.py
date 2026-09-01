"""Black-box local journey used by evaluator and frontend integration smoke."""

from typing import Any

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository

from .scenarios import flagship_participants

JOURNEY_TABLE_ID = "journey-demo"
JOURNEY_CORE_QUESTION = "AI Agent 真正进入企业，卡住的是技术还是采购？"
JOURNEY_ACTOR_ID = "architect"
JOURNEY_MESSAGE_ID = "journey-demo-message-1"
JOURNEY_TEXT = "我亲历过企业采购，试点预算和责任归属仍是上线瓶颈。"


def _expect(response: Any, status_code: int, label: str) -> dict[str, Any]:
    if response.status_code != status_code:
        raise RuntimeError(f"{label} failed ({response.status_code}): {response.text}")
    return response.json()


def _receive_until(websocket: Any, event_type: str, *, limit: int = 8) -> dict[str, Any]:
    for _ in range(limit):
        event = websocket.receive_json()
        if event.get("type") == event_type:
            return event
    raise RuntimeError(f"did not receive {event_type} within {limit} WebSocket events")


def run_journey_demo() -> dict[str, Any]:
    """Run one deterministic journey through the public API and return a report.

    The repository is intentionally in-memory, so repeated invocations cannot
    overwrite a user's JSON demo file or leave a closed table behind.
    """
    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository))
    participant_payload = [
        participant.model_dump(mode="json") for participant in flagship_participants[:4]
    ]
    created = _expect(
        client.post(
            "/tables",
            json={
                "table_id": JOURNEY_TABLE_ID,
                "core_question": JOURNEY_CORE_QUESTION,
                "participants": participant_payload,
            },
        ),
        201,
        "create table",
    )
    lobby = _expect(
        client.get(f"/tables/{JOURNEY_TABLE_ID}/lobby"), 200, "load lobby"
    )

    with client.websocket_connect(
        f"/ws/tables/{JOURNEY_TABLE_ID}?participant_id={JOURNEY_ACTOR_ID}"
    ) as websocket:
        websocket.send_json(
            {
                "type": "human_message",
                "message_id": JOURNEY_MESSAGE_ID,
                "participant_id": JOURNEY_ACTOR_ID,
                "text": JOURNEY_TEXT,
                "client_ts": 1756728000000,
            }
        )
        message = _receive_until(websocket, "message_committed")
        action_event: dict[str, Any] | None = None
        state_event = None
        for _ in range(8):
            event = websocket.receive_json()
            if event.get("type") == "agent_action":
                action_event = event
            if event.get("type") == "table_state_changed":
                state_event = event
                break
        if state_event is None:
            raise RuntimeError("did not receive table_state_changed after human turn")

        websocket.send_json({"type": "request_close"})
        close_started = _receive_until(websocket, "close_started")
        close_artifact = _receive_until(websocket, "close_artifact_ready")
        closed_state = _receive_until(websocket, "table_state_changed")

    evaluation = _expect(
        client.get(
            f"/tables/{JOURNEY_TABLE_ID}/evaluation?participant_id={JOURNEY_ACTOR_ID}"
        ),
        200,
        "load evaluation",
    )
    replay = _expect(
        client.get(
            f"/tables/{JOURNEY_TABLE_ID}/replay?participant_id={JOURNEY_ACTOR_ID}"
        ),
        200,
        "load replay",
    )
    first_message = next(
        item for item in replay["messages"] if item["message_id"] == JOURNEY_MESSAGE_ID
    )

    public_action = None
    if action_event is not None:
        public_action = {
            key: action_event.get(key)
            for key in (
                "action",
                "target_participant_id",
                "text",
                "evidence_turns",
                "state_version",
                "confidence",
            )
        }

    return {
        "table_id": JOURNEY_TABLE_ID,
        "core_question": JOURNEY_CORE_QUESTION,
        "steps": {
            "table_created": created["table_id"] == JOURNEY_TABLE_ID,
            "lobby_loaded": lobby["table_id"] == JOURNEY_TABLE_ID,
            "human_turn_committed": message["type"] == "message_committed",
            "close_started": close_started["type"] == "close_started",
            "close_artifact_ready": close_artifact["type"] == "close_artifact_ready",
            "table_closed": closed_state["state"]["conversation"]["closed"] is True,
        },
        "lobby": lobby,
        "turn": {
            "message_id": first_message["message_id"],
            "turn_id": first_message["turn_id"],
            "participant_id": first_message["participant_id"],
            "agent_action": public_action,
        },
        "close_artifacts": {
            "state_version": close_artifact["state_version"],
            "shared_baseline": close_artifact["shared_baseline"],
            "personal_card": close_artifact["personal_card"],
        },
        "evaluation": evaluation,
        "replay_summary": {
            "message_count": len(replay["messages"]),
            "snapshot_count": len(replay["snapshots"]),
            "intervention_count": len(replay["interventions"]),
            "source_signal_count": len(replay.get("source_signals", [])),
            "closed": replay["snapshots"][-1]["conversation"]["closed"] is True,
        },
    }


__all__ = (
    "JOURNEY_ACTOR_ID",
    "JOURNEY_CORE_QUESTION",
    "JOURNEY_MESSAGE_ID",
    "JOURNEY_TABLE_ID",
    "run_journey_demo",
)
