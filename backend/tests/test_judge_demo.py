import asyncio
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.demo.service import DemoTiming, JudgeDemoService
from app.domain.schemas import HumanTurn, SimulationGeneration


class Provider:
    model = "test-conversation"

    def __init__(self):
        self.calls = []
        self.text_value = "你说怕打扰朋友，我也有过。后来约好一个能聊十分钟的时间，心里反而轻松了。"

    async def text(self, task, messages, config=None):
        self.calls.append((task, messages, config))
        return self.text_value


FAST = DemoTiming(debounce=0.005, reply_gap=0.01, idle=0.08, typing_ttl=0.08, timeout=0.15)


async def wait_until(predicate, timeout=1):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.003)


async def service_fixture(provider=None, timing=FAST):
    repo, provider, events = InMemoryTableRepository(), provider or Provider(), []

    async def broadcast(table_id, payload):
        events.append(payload)

    async def commit(table_id, pid, text, mid, **options):
        options.pop("orchestrate", None)
        state, created = repo.append_message_once(table_id, pid, text, mid, **options)
        assert created
        events.append({"type": "message_committed", "text": text})
        return state

    service = JudgeDemoService(repo, provider, enabled=True, commit=commit, broadcast=broadcast, timing=timing)
    state, _ = await service.create("judge", "我", "run-1")
    return service, repo, provider, events, state.table_id


def test_demo_disabled_and_missing_provider_are_explicit():
    with TestClient(create_app()) as client:
        assert client.get("/demo/cases/ai_friendship").status_code == 404
        assert client.post("/demo/sessions", json={"participant_id": "j", "request_id": "r"}).status_code == 404
    with TestClient(create_app(enable_judge_demo=True)) as client:
        assert client.get("/demo/cases/ai_friendship").json()["available"] is False
        assert client.post("/demo/sessions", json={"participant_id": "j", "request_id": "r"}).status_code == 503


def test_session_isolation_idempotency_and_json_reload(tmp_path):
    path = tmp_path / "sessions.json"
    repo = JsonTableRepository(path)
    with TestClient(create_app(repo, Provider(), enable_judge_demo=True)) as client:
        first = client.post("/demo/sessions", json={"participant_id": "judge", "request_id": "r1"})
        repeated = client.post("/demo/sessions", json={"participant_id": "judge", "request_id": "r1"})
        second = client.post("/demo/sessions", json={"participant_id": "judge", "request_id": "r2"})
        assert first.status_code == 201 and repeated.status_code == 200
        assert first.json() == repeated.json()
        assert first.json()["table_id"] != second.json()["table_id"]
        a, b = first.json()["state"], second.json()["state"]
        assert len(a["participants"]) == 4 and a["agent"]["agent_id"] == "roundtable-agent"
        assert not set(a["demo"]["simulated_participant_ids"]) & set(b["demo"]["simulated_participant_ids"])
        descriptor = client.get("/demo/cases/ai_friendship").json()
        assert "experiences" not in json.dumps(descriptor)
        assert {p["persona_id"] for p in descriptor["participants"]} == {"xiaoxu", "azhou", "linlin"}
    loaded = JsonTableRepository(path)
    assert loaded.get(a["table_id"]).demo.owner_participant_id == "judge"
    assert len(loaded.turns(a["table_id"])) == 2
    assert all(t.source == "simulated" and t.generation.kind == "opening" for t in loaded.turns(a["table_id"]))
    assert not loaded.turns(b["table_id"]) == []


def test_legacy_turn_contract_remains_unchanged():
    assert HumanTurn(turn_id=1, participant_id="p", text="hello").model_dump(mode="json") == {
        "turn_id": 1, "participant_id": "p", "text": "hello"}
    with pytest.raises(ValueError):
        HumanTurn(turn_id=1, participant_id="p", text="hello", source="simulated")


def test_simulated_identity_cannot_be_spoofed_or_joined_or_saved():
    repo = InMemoryTableRepository()
    with TestClient(create_app(repo, Provider(), enable_judge_demo=True)) as client:
        session = client.post("/demo/sessions", json={"participant_id": "judge", "request_id": "r"}).json()
        tid = session["table_id"]
        simulated = session["state"]["demo"]["simulated_participant_ids"][0]
        with client.websocket_connect(f"/ws/tables/{tid}?participant_id={simulated}") as ws:
            assert ws.receive_json()["code"] == "demo_owner_only"
        with pytest.raises(ValueError, match="source"):
            repo.append_message_once(tid, simulated, "pretend", "spoof")
        add = client.post(f"/tables/{tid}/participants?inviter_id=judge", json={"participant_id": "extra", "display_name": "extra", "role": "member", "declared_position": "hi"})
        assert add.status_code == 409
        assert client.post(f"/demo/sessions/{tid}/resume?participant_id=other").status_code == 403
        assert client.post(f"/tables/{tid}/relationships/{simulated}/save?participant_id=judge").status_code == 409
        assert client.post(f"/tables/{tid}/stage-summaries/request?participant_id={simulated}").status_code == 403
        assert client.get(f"/tables/{tid}/replay?participant_id=other").status_code == 403
        assert client.get("/tables/discovery").json() == []
        assert client.get("/tables").json() == []
        assert len(client.get("/tables?participant_id=judge").json()) == 1


def test_speaker_selection_mentions_and_balance():
    async def exercise():
        service, repo, _, _, tid = await service_fixture()
        repo.append_message_once(tid, "judge", "小许，你有被 AI 误解过吗？", "judge-1")
        assert service.select_speaker(repo.get(tid), repo.turns(tid))["persona_id"] == "xiaoxu"
        other, *_ = await service_fixture()
        assert other.select_speaker(other.repository.get(tid), other.repository.turns(tid))["persona_id"] != "azhou"
    asyncio.run(exercise())


def test_idle_is_bounded_and_only_runs_while_owner_connected():
    async def exercise():
        service, repo, provider, events, tid = await service_fixture()
        await asyncio.sleep(0.09)
        assert not provider.calls
        await service.connected(tid, "judge")
        await wait_until(lambda: len(provider.calls) == 1)
        await asyncio.sleep(0.2)
        assert len(provider.calls) == 1
        assert [e["status"] for e in events if e["type"] == "participant_response_status"] == ["thinking", "idle"]
        await service.disconnected(tid, "judge")
        assert not service._tasks
    asyncio.run(exercise())


def test_typing_heartbeat_holds_generation_and_false_resumes():
    async def exercise():
        service, repo, provider, events, tid = await service_fixture()
        await service.connected(tid, "judge")
        repo.append_message_once(tid, "judge", "我想补充一点。", "j1")
        await service.owner_message(tid)
        await service.typing(tid, "judge", True)
        await asyncio.sleep(0.025)
        await service.typing(tid, "judge", True)
        await asyncio.sleep(0.025)
        assert not provider.calls
        assert any(e.get("status") == "paused" for e in events)
        await service.typing(tid, "judge", False)
        await wait_until(lambda: len(provider.calls) == 1)
        await service.close()
    asyncio.run(exercise())


def test_new_judge_turn_discards_cancel_resistant_old_response():
    class Slow(Provider):
        async def text(self, task, messages, config=None):
            self.calls.append((task, messages, config))
            if len(self.calls) == 1:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    return "这是旧话题的过时回答。"
            return "你刚才改说隐私，我也会介意聊天被别人看到。"

    async def exercise():
        service, repo, provider, _, tid = await service_fixture(Slow())
        await service.connected(tid, "judge")
        repo.append_message_once(tid, "judge", "说说陪伴吧。", "j1")
        await service.owner_message(tid)
        await wait_until(lambda: len(provider.calls) == 1)
        repo.append_message_once(tid, "judge", "先不聊陪伴，我更担心隐私。", "j2")
        await service.owner_message(tid)
        await wait_until(lambda: len(repo.turns(tid)) == 5)
        assert not any("过时" in t.text for t in repo.turns(tid))
        assert "隐私" in json.loads(provider.calls[-1][1][-1]["content"])["recent_turns"][-1]["text"]
        await service.close()
    asyncio.run(exercise())


def test_timeout_is_visible_without_fabricated_fallback_speech():
    class Slow(Provider):
        async def text(self, task, messages, config=None):
            self.calls.append(task)
            await asyncio.sleep(1)

    async def exercise():
        service, repo, _, events, tid = await service_fixture(Slow(), replace(FAST, timeout=0.015))
        await service.connected(tid, "judge")
        repo.append_message_once(tid, "judge", "你们怎么看？", "j1")
        await service.owner_message(tid)
        await wait_until(lambda: any(e.get("status") == "failed" for e in events))
        assert len(repo.turns(tid)) == 3
        assert "API" not in next(e["detail"] for e in events if e.get("status") == "failed")
        await service.close()
    asyncio.run(exercise())


def test_close_cancels_no_late_write_even_when_provider_ignores_cancel():
    class Slow(Provider):
        async def text(self, task, messages, config=None):
            self.calls.append(task)
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                return "我还想补充一句。"

    async def exercise():
        service, repo, provider, events, tid = await service_fixture(Slow())
        await service.connected(tid, "judge")
        repo.append_message_once(tid, "judge", "说说吧。", "j1")
        await service.owner_message(tid)
        await wait_until(lambda: bool(provider.calls))
        await service.stop(tid)
        repo.close_table(tid)
        await asyncio.sleep(0.025)
        assert len(repo.turns(tid)) == 3
        assert events[-1]["status"] == "idle"
        assert not service._tasks
    asyncio.run(exercise())


def test_summary_pauses_and_then_resumes_with_fresh_context():
    async def exercise():
        service, repo, provider, _, tid = await service_fixture()
        await service.connected(tid, "judge")
        repo.append_message_once(tid, "judge", "你们怎么看？", "j1")
        await service.owner_message(tid)
        await service.summary_started(tid)
        await asyncio.sleep(0.025)
        assert not provider.calls
        await service.summary_finished(tid)
        await wait_until(lambda: bool(provider.calls))
        await service.close()
    asyncio.run(exercise())


def test_stop_from_own_commit_does_not_cancel_or_await_itself():
    async def exercise():
        service, repo, _, events, tid = await service_fixture()
        original_commit = service.commit

        async def closing_commit(*args, **kwargs):
            state = await original_commit(*args, **kwargs)
            await service.stop(tid)
            repo.close_table(tid)
            return state

        service.commit = closing_commit
        await service.connected(tid, "judge")
        repo.append_message_once(tid, "judge", "你说说吧。", "j1")
        await service.owner_message(tid)
        await wait_until(lambda: repo.get(tid).conversation.closed)
        assert len(repo.turns(tid)) == 4
        assert not any(e.get("status") == "failed" for e in events)
        assert not service._tasks
    asyncio.run(exercise())


def test_closing_freeze_survives_reconnect_and_retry():
    async def exercise():
        service, _, provider, _, tid = await service_fixture()
        await service.connected(tid, "judge")
        await service.stop(tid, closing=True)
        await service.disconnected(tid, "judge")
        await service.connected(tid, "judge")
        with pytest.raises(ValueError):
            await service.resume(tid, "judge")
        await asyncio.sleep(0.1)
        assert not provider.calls
        assert not service._tasks
        await service.close()
    asyncio.run(exercise())


def test_two_replies_maximum_per_judge_turn_then_waits():
    async def exercise():
        service, repo, provider, _, tid = await service_fixture()
        await service.connected(tid, "judge")
        repo.append_message_once(tid, "judge", "大家怎么看？", "j1")
        await service.owner_message(tid)
        await wait_until(lambda: len(provider.calls) == 2)
        await asyncio.sleep(0.15)
        assert len(provider.calls) == 2
        assert service.remaining(repo.get(tid), repo.turns(tid)) == 0
        await service.close()
    asyncio.run(exercise())


def test_websocket_real_flow_status_commit_replay_and_typing():
    provider, repo = Provider(), InMemoryTableRepository()
    with TestClient(create_app(repo, provider, enable_judge_demo=True, judge_demo_timing=replace(FAST, idle=1))) as client:
        session = client.post("/demo/sessions", json={"participant_id": "judge", "request_id": "flow"}).json()
        tid = session["table_id"]
        with client.websocket_connect(f"/ws/tables/{tid}?participant_id=judge") as ws:
            ws.send_json({"type": "participant_typing", "is_typing": True})
            ws.send_json({"type": "human_message", "participant_id": "judge", "message_id": "j1", "text": "小许，你怕不怕打扰朋友？", "client_ts": 1})
            events = []
            for _ in range(20):
                item = ws.receive_json()
                events.append(item)
                if item["type"] == "message_committed" and item["message"].get("source") == "simulated":
                    break
            judge_message = next(e["message"] for e in events if e["type"] == "message_committed" and e["message"]["participant_id"] == "judge")
            assert judge_message["turn_id"] == 3
            simulated = events[-1]["message"]
            assert simulated["generation"]["model"] == "test-conversation"
            assert simulated["participant_id"].endswith(":xiaoxu")
            status_index = next(i for i, e in enumerate(events) if e.get("participant_id") == simulated["participant_id"] and e.get("status") == "thinking")
            assert status_index < len(events) - 1
        replay = client.get(f"/tables/{tid}/replay?participant_id=judge").json()
        assert any(t.get("generation", {}).get("kind") == "llm" for t in replay["messages"])
