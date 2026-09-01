import asyncio
import json
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.domain import Action, GateDecision, RouteDecision
from app.sources import CommandContentSignalSource, ContentSignalSourceError


class _Source:
    def __init__(self, signals):
        self.signals = signals
        self.calls = []

    async def search(self, *, query, limit):
        self.calls.append((query, limit))
        return self.signals[:limit]


class _HangingSource:
    async def search(self, *, query, limit):
        await asyncio.sleep(0.2)
        return []


def _table(client: TestClient, table_id: str = "grounding-table") -> None:
    response = client.post("/tables", json={
        "table_id": table_id,
        "core_question": "企业 Agent 如何落地？",
        "participants": [
            {"participant_id": "p1", "display_name": "p1", "role": "产品", "declared_position": "看价值"},
            {"participant_id": "p2", "display_name": "p2", "role": "架构师", "declared_position": "看技术"},
        ],
    })
    assert response.status_code == 201


def _signal(signal_id: str, author_id: str, content_type: str = "answer") -> dict:
    return {
        "signal_id": signal_id,
        "content_type": content_type,
        "title": "企业 Agent 如何落地？",
        "excerpt": "试点需要明确责任和验收边界。",
        "source_ref": f"authorized:public:{signal_id}",
        "author_id": author_id,
        "author_name": author_id,
        "author_role": "产品" if author_id == "u1" else "架构师",
        "public_stance": "先验证价值" if author_id == "u1" else "先解决技术边界",
    }


def test_source_opportunity_preview_reuses_detector_and_preserves_public_contract() -> None:
    source = _Source([_signal("s1", "u1", "question"), _signal("s2", "u2")])
    client = TestClient(create_app(content_source=source))

    response = client.post(
        "/opportunities/source-preview",
        json={"query": "企业 Agent 如何落地？", "limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["core_question"] == "企业 Agent 如何落地？"
    assert payload["signal_ids"] == ["s1", "s2"]
    assert {item["participant_id"] for item in payload["candidates"]} == {"u1", "u2"}
    assert source.calls == [("企业 Agent 如何落地？", 2)]


def test_grounding_endpoint_stages_public_card_for_the_real_ground_action() -> None:
    source = _Source([_signal("s1", "u1"), _signal("s2", "u2")])
    client = TestClient(create_app(content_source=source))
    _table(client)

    staged = client.post(
        "/tables/grounding-table/grounding?participant_id=p1",
        json={"query": "企业 Agent 责任边界", "limit": 2},
    )

    assert staged.status_code == 200
    assert staged.json() == {
        "title": "企业 Agent 如何落地？",
        "excerpt": "试点需要明确责任和验收边界。",
        "source_ref": "authorized:public:s1",
        "signal_id": "s1",
    }
    assert source.calls == [("企业 Agent 责任边界", 2)]
    assert client.get("/tables/grounding-table/state").json()["version"] == 0

    decision = (
        GateDecision(should_speak=True, evidence_turns=[1], reasons_to_speak=["ground"], confidence=.9),
        RouteDecision(action=Action.GROUND, evidence_turns=[1], confidence=.9),
    )
    with patch("app.api.websocket.decide_intervention", return_value=decision):
        with client.websocket_connect("/ws/tables/grounding-table?participant_id=p1") as websocket:
            websocket.send_json({
                "type": "human_message",
                "message_id": "grounding-message",
                "participant_id": "p1",
                "text": "这个事实需要核对。",
                "client_ts": 1756728000000,
            })
            assert websocket.receive_json()["type"] == "message_committed"
            action = websocket.receive_json()
            card = websocket.receive_json()
            assert websocket.receive_json()["type"] == "table_state_changed"

    assert action["action"] == "GROUND"
    assert card["type"] == "grounding_card"
    assert card["source_ref"] == "authorized:public:s1"
    assert card["signal_id"] == "s1"
    assert source.calls == [("企业 Agent 责任边界", 2)]
    replay = client.get("/tables/grounding-table/replay").json()
    assert replay["interventions"][0]["grounding_card"] == {
        "title": "企业 Agent 如何落地？",
        "excerpt": "试点需要明确责任和验收边界。",
        "source_ref": "authorized:public:s1",
        "signal_id": "s1",
    }


def test_grounding_card_is_used_after_observer_detects_opposite_fact_turns() -> None:
    source = _Source([_signal("s1", "u1"), _signal("s2", "u2")])
    client = TestClient(create_app(content_source=source))
    _table(client, "grounding-observer")
    staged = client.post(
        "/tables/grounding-observer/grounding?participant_id=p1",
        json={"query": "企业 Agent 责任边界", "limit": 2},
    )
    assert staged.status_code == 200

    with client.websocket_connect("/ws/tables/grounding-observer?participant_id=p1") as observer, \
            client.websocket_connect("/ws/tables/grounding-observer?participant_id=p2") as challenger:
        observer.send_json({
            "type": "human_message",
            "message_id": "fact-1",
            "participant_id": "p1",
            "text": "采购需要预算。",
            "client_ts": 1756728000000,
        })
        assert observer.receive_json()["type"] == "message_committed"
        assert observer.receive_json()["type"] == "table_state_changed"

        challenger.send_json({
            "type": "human_message",
            "message_id": "fact-2",
            "participant_id": "p2",
            "text": "采购不需要预算。",
            "client_ts": 1756728001000,
        })
        events = {}
        for _ in range(4):
            event = observer.receive_json()
            events[event["type"]] = event

    assert events["message_committed"]["message"]["message_id"] == "fact-2"
    assert events["agent_action"]["action"] == "GROUND"
    assert events["grounding_card"]["signal_id"] == "s1"
    assert events["table_state_changed"]["state"]["version"] == 3
    replay = client.get("/tables/grounding-observer/replay").json()
    assert replay["interventions"][0]["grounding_card"]["signal_id"] == "s1"


def test_grounding_endpoint_is_member_scoped_and_fails_closed_on_missing_results() -> None:
    source = _Source([])
    client = TestClient(create_app(content_source=source))
    _table(client, "grounding-guards")

    assert client.post(
        "/tables/grounding-guards/grounding?participant_id=ghost", json={}
    ).status_code == 403
    empty = client.post(
        "/tables/grounding-guards/grounding?participant_id=p1", json={}
    )
    assert empty.status_code == 404
    assert empty.json() == {"detail": "no grounding source signal found"}

    missing = TestClient(create_app())
    _table(missing, "grounding-missing")
    response = missing.post(
        "/tables/grounding-missing/grounding?participant_id=p1", json={}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "content source is not configured"}


def test_grounding_endpoint_hides_source_failures_and_respects_table_lifecycle() -> None:
    invalid = _Source([{"signal_id": "only-partial"}])
    invalid_client = TestClient(create_app(content_source=invalid))
    _table(invalid_client, "grounding-invalid")
    invalid_response = invalid_client.post(
        "/tables/grounding-invalid/grounding?participant_id=p1", json={}
    )
    assert invalid_response.status_code == 502
    assert invalid_response.json() == {"detail": "content source returned invalid signals"}

    timeout_client = TestClient(create_app(
        content_source=_HangingSource(), content_source_timeout_seconds=0.01,
    ))
    _table(timeout_client, "grounding-timeout")
    timeout_response = timeout_client.post(
        "/tables/grounding-timeout/grounding?participant_id=p1", json={}
    )
    assert timeout_response.status_code == 502
    assert timeout_response.json() == {"detail": "content source timed out"}

    repository = invalid_client.app.state.repository
    repository.close_table("grounding-invalid")
    closed = invalid_client.post(
        "/tables/grounding-invalid/grounding?participant_id=p1", json={}
    )
    assert closed.status_code == 409
    assert closed.json() == {"detail": "table is closed"}


def test_source_opportunity_preview_fails_closed_without_source_or_with_bad_signals() -> None:
    missing = TestClient(create_app()).post(
        "/opportunities/source-preview", json={"query": "Q"}
    )
    assert missing.status_code == 503
    assert missing.json() == {"detail": "content source is not configured"}

    invalid = _Source([{"signal_id": "only-partial"}])
    client = TestClient(create_app(content_source=invalid))
    response = client.post("/opportunities/source-preview", json={"query": "Q"})
    assert response.status_code == 502
    assert response.json() == {"detail": "content source returned invalid signals"}


def test_source_opportunity_preview_consumes_only_requested_signal_limit() -> None:
    def rows():
        yield _signal("s1", "u1", "question")
        yield _signal("s2", "u2")
        raise AssertionError("source rows beyond the requested limit must not be consumed")

    class _LazySource:
        async def search(self, *, query, limit):
            return rows()

    response = TestClient(create_app(content_source=_LazySource())).post(
        "/opportunities/source-preview",
        json={"query": "企业 Agent 如何落地？", "limit": 2},
    )

    assert response.status_code == 200
    assert response.json()["signal_ids"] == ["s1", "s2"]


def test_source_opportunity_preview_times_out_and_rejects_non_positive_timeout() -> None:
    client = TestClient(create_app(
        content_source=_HangingSource(), content_source_timeout_seconds=0.01,
    ))
    response = client.post("/opportunities/source-preview", json={"query": "Q"})
    assert response.status_code == 502
    assert response.json() == {"detail": "content source timed out"}

    try:
        create_app(content_source_timeout_seconds=0)
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("non-positive content source timeout must be rejected")


def test_command_content_signal_source_uses_bounded_json_contract() -> None:
    script = (
        "import json,sys; request=json.load(sys.stdin); "
        "print(json.dumps({'signals':[{'signal_id':'s1','content_type':'answer',"
        "'title':'题目','excerpt':'摘要','source_ref':'source:1','author_id':'u1',"
        "'author_name':'甲'}]}))"
    )
    source = CommandContentSignalSource([sys.executable, "-c", script])

    signals = asyncio.run(source.search(query="企业 Agent", limit=2))

    assert len(signals) == 1
    assert signals[0].signal_id == "s1"


def test_command_content_signal_source_fails_closed_on_bad_json_and_output_limits() -> None:
    invalid = CommandContentSignalSource([sys.executable, "-c", "print('not-json')"])
    try:
        asyncio.run(invalid.search(query="Q", limit=2))
    except ContentSignalSourceError as error:
        assert "invalid JSON" in str(error)
    else:
        raise AssertionError("invalid content source output must fail")

    oversized = CommandContentSignalSource(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100)"],
        max_output_bytes=16,
    )
    try:
        asyncio.run(oversized.search(query="Q", limit=2))
    except ContentSignalSourceError as error:
        assert "too large" in str(error)
    else:
        raise AssertionError("oversized content source output must fail")


def test_command_content_source_timeout_covers_process_start(monkeypatch) -> None:
    async def blocked_start(*args, **kwargs):
        await asyncio.sleep(0.2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", blocked_start)
    source = CommandContentSignalSource([sys.executable, "-c", "print('{}')"], timeout_seconds=0.01)

    with pytest.raises(ContentSignalSourceError, match="timed out"):
        asyncio.run(source.search(query="Q", limit=2))


def test_runtime_content_source_command_is_configured_as_json_argv(monkeypatch) -> None:
    command = [sys.executable, "-c", "import sys; sys.stdout.write('{\"signals\":[]}')"]
    monkeypatch.setenv("CONTENT_SIGNAL_SOURCE_COMMAND", json.dumps(command))

    from app.main import _build_content_source

    source = _build_content_source()
    assert isinstance(source, CommandContentSignalSource)
    assert tuple(command) == source.command
