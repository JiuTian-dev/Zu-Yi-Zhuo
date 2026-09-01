"""Black-box local journey used by evaluator and frontend integration smoke."""

from typing import Any

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed

from .public_signals import flagship_public_signals

JOURNEY_TABLE_ID = "journey-demo"
JOURNEY_CORE_QUESTION = "AI Agent 真正进入企业，卡住的是技术还是采购？"
JOURNEY_ACTOR_ID = "public-architect"
JOURNEY_MESSAGE_ID = "journey-demo-message-1"
JOURNEY_TEXT = "我亲历过企业采购；我会先和采购团队验证责任归属，再决定是否扩大试点。"
JOURNEY_REPLENISHMENT_ID = "public-practitioner"


class _JourneyCandidateSource:
    """Deterministic fifth-seat source used only by the isolated demo."""

    async def search(self, *, query: str, limit: int) -> list[ParticipantSeed]:
        if limit <= 0:
            return []
        return [ParticipantSeed(
            participant_id=JOURNEY_REPLENISHMENT_ID,
            display_name="公开实践者",
            role="实践者",
            declared_position="先从真实业务的小闭环验证开始",
            relevant_experience=[{
                "text": "参与过企业 AI 试点和责任链验证",
                "source_ref": "demo:public-practitioner:experience",
            }],
        )]


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
    client = TestClient(create_app(repository, candidate_source=_JourneyCandidateSource()))
    opportunity = _expect(
        client.post(
            "/opportunities/preview",
            json={
                "query": JOURNEY_CORE_QUESTION,
                "signals": [signal.model_dump(mode="json") for signal in flagship_public_signals],
            },
        ),
        200,
        "preview opportunity",
    )
    matched = _expect(
        client.post(
            "/matches/confirm",
            json={
                "table_id": JOURNEY_TABLE_ID,
                "core_question": opportunity["core_question"],
                "candidates": opportunity["candidates"],
                "table_size": 4,
                "origin_signal_ids": opportunity["signal_ids"],
                "origin_signals": opportunity["source_signals"],
            },
        ),
        201,
        "confirm match",
    )
    created = matched["state"]
    candidate_preview = _expect(
        client.post(
            f"/tables/{JOURNEY_TABLE_ID}/candidate-preview?participant_id={JOURNEY_ACTOR_ID}",
            json={"limit": 1},
        ),
        200,
        "preview replenishment candidate",
    )
    recommendation = candidate_preview["candidates"][0]
    invitation = _expect(
        client.post(
            f"/tables/{JOURNEY_TABLE_ID}/invitations/from-preview?inviter_id={JOURNEY_ACTOR_ID}",
            json={"preview_token": recommendation["preview_token"]},
        ),
        201,
        "create replenishment invitation",
    )
    accepted = _expect(
        client.post(
            f"/tables/{JOURNEY_TABLE_ID}/invitations/{invitation['invitation_id']}/respond?participant_id={JOURNEY_REPLENISHMENT_ID}",
            json={"accept": True},
        ),
        200,
        "accept replenishment invitation",
    )
    created = accepted["state"]
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

    follow_ups = _expect(
        client.get(
            f"/tables/{JOURNEY_TABLE_ID}/follow-ups?participant_id={JOURNEY_ACTOR_ID}"
        ),
        200,
        "load follow-ups",
    )
    if not follow_ups:
        raise RuntimeError("journey message did not produce a follow-up item")
    follow_up = follow_ups[0]
    outcome = _expect(
        client.post(
            f"/tables/{JOURNEY_TABLE_ID}/follow-ups/{follow_up['follow_up_index']}/outcome?participant_id={JOURNEY_ACTOR_ID}",
            json={"status": "completed", "note": "已完成第一轮采购责任链验证"},
        ),
        200,
        "record follow-up outcome",
    )
    feedback = _expect(
        client.post(
            f"/tables/{JOURNEY_TABLE_ID}/feedback?participant_id={JOURNEY_ACTOR_ID}",
            json={
                "cognitive_value": 5,
                "relationship_value": 4,
                "action_value": 5,
                "emotional_value": 4,
                "note": "带走了一个可以验证的下一步",
                "would_join_again": True,
            },
        ),
        200,
        "submit value feedback",
    )
    evaluation = _expect(
        client.get(
            f"/tables/{JOURNEY_TABLE_ID}/evaluation?participant_id={JOURNEY_ACTOR_ID}"
        ),
        200,
        "load evaluation",
    )
    action_echoes = _expect(
        client.get(
            f"/participants/{JOURNEY_ACTOR_ID}/action-echoes?viewer_id={JOURNEY_ACTOR_ID}"
        ),
        200,
        "load action echoes",
    )
    behavior_events = _expect(
        client.get(
            f"/participants/{JOURNEY_ACTOR_ID}/behavior-events?viewer_id={JOURNEY_ACTOR_ID}"
        ),
        200,
        "load behavior events",
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
            "opportunity_previewed": opportunity["core_question"] == JOURNEY_CORE_QUESTION,
            "match_confirmed": matched["plan"]["core_question"] == JOURNEY_CORE_QUESTION,
            "table_created": created["table_id"] == JOURNEY_TABLE_ID,
            "candidate_previewed": bool(candidate_preview["candidates"]),
            "invitation_created": invitation["status"] == "pending",
            "candidate_joined": JOURNEY_REPLENISHMENT_ID in created["participants"],
            "lobby_loaded": lobby["table_id"] == JOURNEY_TABLE_ID,
            "human_turn_committed": message["type"] == "message_committed",
            "close_started": close_started["type"] == "close_started",
            "close_artifact_ready": close_artifact["type"] == "close_artifact_ready",
            "table_closed": closed_state["state"]["conversation"]["closed"] is True,
        },
        "opportunity": {
            "core_question": opportunity["core_question"],
            "signal_ids": opportunity["signal_ids"],
            "unfinishedness": opportunity["unfinishedness"],
            "role_gaps": opportunity["role_gaps"],
            "candidate_ids": [item["participant_id"] for item in opportunity["candidates"]],
        },
        "match": {
            "selected": matched["plan"]["selected"],
            "reasons": matched["plan"]["reasons"],
            "unmatched_participant_ids": matched["plan"]["unmatched_participant_ids"],
        },
        "replenishment": {
            "candidate": {
                "participant_id": recommendation["participant_id"],
                "display_name": recommendation["display_name"],
                "role": recommendation["role"],
                "reason": recommendation["reason"],
                "evidence_signal_ids": recommendation.get("evidence_signal_ids", []),
            },
            "invitation": invitation,
            "accepted": accepted["invitation"],
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
        "post_close": {
            "follow_up": follow_up,
            "outcome": outcome,
            "feedback": feedback,
            "action_echoes": action_echoes,
            "behavior_event_types": [item["event_type"] for item in behavior_events],
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
    "JOURNEY_REPLENISHMENT_ID",
    "JOURNEY_TABLE_ID",
    "run_journey_demo",
)
