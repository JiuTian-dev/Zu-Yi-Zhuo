"""Isolated black-box proof of the authorized-source GROUND path."""

from typing import Any

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ContentSignal

GROUNDING_TABLE_ID = "grounding-demo"
GROUNDING_SOURCE_ID = "grounding-demo-signal"


class _GroundingSource:
    async def search(self, *, query: str, limit: int) -> list[ContentSignal]:
        if limit <= 0:
            return []
        return [ContentSignal(
            signal_id=GROUNDING_SOURCE_ID,
            content_type="answer",
            title="企业 Agent 的预算责任边界",
            excerpt="试点预算与正式采购预算由不同责任链承接。",
            source_ref="demo:public:grounding",
            author_id="public-researcher",
            author_name="公开研究者",
            author_role="企业研究者",
            public_stance="先核对责任链，再判断采购结论",
            visibility="public",
        )]


def _expect(response: Any, status_code: int, label: str) -> dict[str, Any]:
    if response.status_code != status_code:
        raise RuntimeError(f"{label} failed ({response.status_code}): {response.text}")
    return response.json()


def _until(websocket: Any, event_type: str, *, limit: int = 8) -> dict[str, Any]:
    for _ in range(limit):
        event = websocket.receive_json()
        if event.get("type") == event_type:
            return event
    raise RuntimeError(f"did not receive {event_type} within {limit} WebSocket events")


def run_grounding_demo() -> dict[str, Any]:
    """Drive source grounding, fact detection, GROUND and replay via real APIs."""

    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository, content_source=_GroundingSource()))
    _expect(client.post("/tables", json={
        "table_id": GROUNDING_TABLE_ID,
        "core_question": "企业 Agent 的采购预算责任如何核对？",
        "participants": [
            {"participant_id": "p1", "display_name": "产品负责人", "role": "产品", "declared_position": "先看业务预算"},
            {"participant_id": "p2", "display_name": "架构师", "role": "架构师", "declared_position": "先看技术边界"},
        ],
    }), 201, "create grounding table")
    card = _expect(client.post(
        f"/tables/{GROUNDING_TABLE_ID}/grounding?participant_id=p1",
        json={"query": "采购预算责任", "limit": 1},
    ), 200, "stage grounding card")

    with client.websocket_connect(f"/ws/tables/{GROUNDING_TABLE_ID}?participant_id=p1") as first, \
            client.websocket_connect(f"/ws/tables/{GROUNDING_TABLE_ID}?participant_id=p2") as second:
        first.send_json({
            "type": "human_message", "message_id": "grounding-demo-1",
            "participant_id": "p1", "text": "采购需要预算。", "client_ts": 1756728000000,
        })
        _until(first, "message_committed")
        _until(first, "table_state_changed")
        second.send_json({
            "type": "human_message", "message_id": "grounding-demo-2",
            "participant_id": "p2", "text": "采购不需要预算。", "client_ts": 1756728001000,
        })
        events = [_until(first, event_type) for event_type in (
            "message_committed", "agent_action", "grounding_card", "table_state_changed",
        )]

    replay = _expect(client.get(f"/tables/{GROUNDING_TABLE_ID}/replay"), 200, "load grounding replay")
    final_state = events[-1]["state"]
    conflict = next(
        item for item in final_state["disagreements"] if item["disagreement_type"] == "fact_conflict"
    )
    action = events[1]
    grounded = events[2]
    return {
        "table_id": GROUNDING_TABLE_ID,
        "steps": {
            "source_card_staged": card["signal_id"] == GROUNDING_SOURCE_ID,
            "opposite_fact_turns_committed": len(replay["messages"]) == 2,
            "fact_conflict_detected": conflict["evidence_turns"] == [1, 2],
            "ground_action_broadcast": action["action"] == "GROUND",
            "grounding_card_broadcast": grounded["signal_id"] == GROUNDING_SOURCE_ID,
            "grounding_card_replayed": replay["interventions"][0]["grounding_card"]["signal_id"] == GROUNDING_SOURCE_ID,
        },
        "fact_conflict": {
            "evidence_turns": conflict["evidence_turns"],
            "participant_ids": conflict["participant_ids"],
        },
        "grounding": {
            "action": action["action"],
            "state_version": action["state_version"],
            "signal_id": grounded["signal_id"],
            "source_ref": grounded["source_ref"],
        },
        "replay": {
            "message_count": len(replay["messages"]),
            "intervention_count": len(replay["interventions"]),
            "grounding_signal_ids": [
                item["grounding_card"]["signal_id"]
                for item in replay["interventions"] if item.get("grounding_card")
            ],
        },
    }


__all__ = ("GROUNDING_TABLE_ID", "run_grounding_demo")
