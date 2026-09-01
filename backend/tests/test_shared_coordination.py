from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.api.event_bus import SQLiteEventBus
from app.api.intent_sessions import SQLiteActiveIntentSessionStore, IntentSessionUnavailable
from app.api.match_tickets import SQLiteSourceMatchTicketStore
from app.api.rate_limit import SQLiteMutationRateLimiter
from app.api.repository import JsonTableRepository
from app.api.app import create_app
from app.domain import MatchPlan, MatchReason, MatchSeat, ParticipantSeed
from fastapi.testclient import TestClient


def _seed(identifier: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=identifier,
        display_name=identifier,
        role="产品",
        declared_position="先验证价值",
    )


def test_json_repository_refreshes_other_worker_writes() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "tables.json"
        first = JsonTableRepository(path)
        second = JsonTableRepository(path)

        first.create("shared", "Q", [_seed("p1")])
        assert second.get("shared").version == 0
        second.set_profile_consent("shared", "p1", True)

        current = first.get("shared")
        assert current.version == 1
        assert current.participants["p1"].profile_shared is True
        assert path.with_name(f".{path.name}.lock").exists()


def test_sqlite_rate_limiter_is_shared_and_windowed() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "rate.sqlite"
        now = [1000.0]
        first = SQLiteMutationRateLimiter(path, 1, clock=lambda: now[0])
        second = SQLiteMutationRateLimiter(path, 1, clock=lambda: now[0])

        assert first.allow("client") == (True, 0)
        denied, retry_after = second.allow("client")
        assert denied is False
        assert retry_after == 60
        now[0] += 60.1
        assert second.allow("client") == (True, 0)


def test_sqlite_event_bus_is_ordered_and_bounded() -> None:
    with TemporaryDirectory() as directory:
        bus = SQLiteEventBus(Path(directory) / "events.sqlite")
        first = bus.publish(channel="table:a", payload={"type": "message_committed"})
        second = bus.publish(channel="table:b", payload={"type": "table_state_changed"})

        events = bus.read_since(cursor=first - 1, limit=10)
        assert [event.event_id for event in events] == [first, second]
        assert [event.channel for event in events] == ["table:a", "table:b"]
        assert bus.latest_id() == second
        assert bus.trim_before(event_id=second) == 1
        assert [event.event_id for event in bus.read_since(cursor=0)] == [second]


def test_sqlite_ephemeral_handoffs_survive_worker_recreation_and_claim_once() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "ephemeral.sqlite"
        plan = MatchPlan(
            core_question="Q",
            selected=[MatchSeat(participant_id="p1", display_name="p1", role="产品"),
                      MatchSeat(participant_id="p2", display_name="p2", role="技术")],
            reasons=[MatchReason(participant_id="p1", reason="角色互补"),
                     MatchReason(participant_id="p2", reason="角色互补")],
        )
        first = SQLiteSourceMatchTicketStore(path, clock=lambda: 1000.0)
        token = first.issue(
            core_question="Q",
            table_size=2,
            candidates=[_seed("p1"), _seed("p2")],
            plan=plan,
        )
        second = SQLiteSourceMatchTicketStore(path, clock=lambda: 1000.0)
        claimed = second.claim(token)
        assert claimed.core_question == "Q"
        try:
            first.claim(token)
        except ValueError as error:
            assert "unavailable" in str(error)
        else:
            raise AssertionError("a claimed ticket must not be claimable twice")
        second.release(token)
        assert first.claim(token).table_size == 2

        sessions = SQLiteActiveIntentSessionStore(path, clock=lambda: 1000.0)
        session = sessions.create(participant_id="alice", message="我想找人聊", limit=4)
        recreated = SQLiteActiveIntentSessionStore(path, clock=lambda: 1000.0)
        assert recreated.get(session.session_id, "alice").messages == ("我想找人聊",)
        updated = recreated.append(session.session_id, "alice", "关于城市徒步")
        assert sessions.get(session.session_id, "alice").turn_count == 2
        assert updated.messages[-1] == "关于城市徒步"
        with pytest.raises(IntentSessionUnavailable):
            sessions.get(session.session_id, "bob")


def test_websocket_events_cross_worker_via_shared_event_bus() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository_path = root / "tables.json"
        bus = SQLiteEventBus(root / "events.sqlite")
        writer_repo = JsonTableRepository(repository_path)
        writer_repo.create("shared-ws", "Q", [_seed("p1"), _seed("p2")])
        reader_repo = JsonTableRepository(repository_path)
        writer = TestClient(create_app(writer_repo, event_bus=bus))
        reader = TestClient(create_app(reader_repo, event_bus=bus))
        with writer, reader:
            with writer.websocket_connect("/ws/tables/shared-ws?participant_id=p1") as first, \
                    reader.websocket_connect("/ws/tables/shared-ws?participant_id=p2") as second:
                first.send_json({
                    "type": "human_message",
                    "message_id": "shared-message-1",
                    "participant_id": "p1",
                    "text": "我补充一条现场经验。",
                    "client_ts": 1,
                })
                local = first.receive_json()
                forwarded = second.receive_json()
                assert local["type"] == "message_committed"
                assert forwarded["type"] == "message_committed"
                assert forwarded["message"]["message_id"] == "shared-message-1"
