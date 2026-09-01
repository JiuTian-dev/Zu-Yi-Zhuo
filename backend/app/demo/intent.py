"""Isolated black-box demo for the active-demand second entry point."""

from typing import Any

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


INTENT_DEMO_USER_ID = "intent-demo-user"
INTENT_DEMO_TABLE_ID = "intent-demo-table"
INTENT_DEMO_FIRST_MESSAGE = "找人聊"
INTENT_DEMO_CLARIFICATION = "我想找人聊城市徒步路线和装备选择"


class _IntentDemoCandidateSource:
    """Deterministic authorized-source stand-in; never reaches the network."""

    async def search(self, *, query: str, limit: int) -> list[ParticipantSeed]:
        candidates = [
            ParticipantSeed(
                participant_id="intent-practitioner",
                display_name="公开实践者",
                role="实践者",
                declared_position="先走过一条路线，再讨论装备取舍",
            ),
            ParticipantSeed(
                participant_id="intent-professional",
                display_name="公开专业者",
                role="专业者",
                declared_position="把安全和体能边界说清楚",
            ),
            ParticipantSeed(
                participant_id="intent-beginner",
                display_name="公开新手",
                role="处境者",
                declared_position="刚开始尝试周末徒步",
            ),
            ParticipantSeed(
                participant_id="intent-bridge",
                display_name="公开桥梁者",
                role="桥梁者",
                declared_position="熟悉城市公共交通和路线信息",
            ),
        ]
        return candidates[:limit]


def _expect(response: Any, status_code: int, label: str) -> dict[str, Any]:
    if response.status_code != status_code:
        raise RuntimeError(f"{label} failed ({response.status_code}): {response.text}")
    return response.json()


def run_intent_demo() -> dict[str, Any]:
    """Run the second-entry path through real HTTP contracts in memory only."""
    repository = InMemoryTableRepository()
    client = TestClient(create_app(
        repository,
        candidate_source=_IntentDemoCandidateSource(),
    ))
    started = _expect(
        client.post(
            f"/participants/{INTENT_DEMO_USER_ID}/intent-sessions?viewer_id={INTENT_DEMO_USER_ID}",
            json={"message": INTENT_DEMO_FIRST_MESSAGE},
        ),
        201,
        "start active intent session",
    )
    session_id = started["session_id"]
    clarified = _expect(
        client.post(
            f"/participants/{INTENT_DEMO_USER_ID}/intent-sessions/{session_id}/turns?viewer_id={INTENT_DEMO_USER_ID}",
            json={"message": INTENT_DEMO_CLARIFICATION},
        ),
        200,
        "clarify active intent session",
    )
    source_preview = _expect(
        client.post(
            f"/participants/{INTENT_DEMO_USER_ID}/intent-sessions/{session_id}/source-preview?viewer_id={INTENT_DEMO_USER_ID}",
            json={"table_size": 4, "limit": 4},
        ),
        200,
        "preview intent candidates",
    )
    confirmed = _expect(
        client.post(
            "/matches/source-confirm",
            json={
                "preview_token": source_preview["preview_token"],
                "table_id": INTENT_DEMO_TABLE_ID,
            },
        ),
        201,
        "confirm intent table",
    )
    return {
        "session": {
            "initial_status": started["status"],
            "final_status": clarified["status"],
            "route": clarified["preview"]["route"],
            "turn_count": clarified["turn_count"],
        },
        "candidate_source_query": source_preview["core_question"],
        "selected_participant_ids": sorted(
            seat["participant_id"] for seat in source_preview["selected"]
        ),
        "table_id": confirmed["state"]["table_id"],
        "participant_count": len(confirmed["state"]["participants"]),
    }


__all__ = ["run_intent_demo"]
