from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


def _seed(participant_id: str, role: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="仅在同桌成员同意后公开",
        relevant_experience=[],
    )


def test_observer_mode_receives_public_state_but_cannot_mutate() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "observer-table",
        "企业为什么难以采用 AI？",
        [_seed("p1", "产品"), _seed("p2", "研究")],
    )
    client = TestClient(create_app(repository))

    with client.websocket_connect(
        "/ws/tables/observer-table?participant_id=guest&viewer_mode=observer"
    ) as observer:
        initial = observer.receive_json()
        assert initial["type"] == "table_state_changed"
        assert initial["state"]["participants"]["p1"]["declared_position"] is None
        assert initial["state"]["participants"]["p1"]["unused_relevant_experience"] == []

        observer.send_json({
            "type": "human_message",
            "message_id": "observer-message",
            "participant_id": "guest",
            "text": "旁听者不应发言",
            "client_ts": 1,
        })
        assert observer.receive_json() == {
            "type": "error",
            "code": "observer_read_only",
            "detail": "observer connections cannot mutate the table",
        }
        observer.send_json({"type": "request_debug_state"})
        debug = observer.receive_json()
        assert debug["state"]["participants"]["p2"]["declared_position"] is None
        assert repository.turns("observer-table") == []


def test_observer_mode_receives_later_public_events_without_becoming_a_seat() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "observer-events",
        "企业为什么难以采用 AI？",
        [_seed("p1", "产品"), _seed("p2", "采购")],
    )
    client = TestClient(create_app(repository))

    with client.websocket_connect(
        "/ws/tables/observer-events?participant_id=guest&viewer_mode=observer"
    ) as observer:
        assert observer.receive_json()["type"] == "table_state_changed"
        with client.websocket_connect("/ws/tables/observer-events?participant_id=p1") as participant:
            participant.send_json({
                "type": "human_message",
                "message_id": "participant-message",
                "participant_id": "p1",
                "text": "我亲历过一次采购试点。",
                "client_ts": 1,
            })
            observer_message = observer.receive_json()
            assert observer_message["type"] == "message_committed"
            assert observer_message["message"]["participant_id"] == "p1"
            while (observer_state := observer.receive_json())["type"] != "table_state_changed":
                pass

            assert observer_state["state"]["version"] > 0
            assert observer_state["state"]["participants"]["p1"]["declared_position"] is None
            assert set(repository.get("observer-events").participants) == {"p1", "p2"}
