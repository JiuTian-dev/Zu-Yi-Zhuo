import json

from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed, SafetyLevel
from app.orchestrator import enforce_safety, evaluate_safety


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="桌内立场",
    )


def test_agent_presence_is_stable_and_not_a_human_seat() -> None:
    repository = InMemoryTableRepository()
    state = repository.create("agent-presence", "Q", [_seed("p1"), _seed("p2")])

    assert state.agent.model_dump(mode="json") == {
        "agent_id": "roundtable-agent",
        "display_name": "圆桌 Agent",
        "role": "对话搭档",
        "status": "active",
    }
    assert set(state.participants) == {"p1", "p2"}

    paused = repository.append_safety_state(
        "agent-presence", enforce_safety(state, evaluate_safety("我要威胁你", 1))
    )
    assert paused.agent.status == "paused"
    assert paused.conversation.safety_level is SafetyLevel.CRITICAL

    closed = repository.close_table("agent-presence")
    assert closed.agent.status == "closed"
    assert set(closed.participants) == {"p1", "p2"}


def test_json_repository_defaults_agent_for_legacy_snapshots(tmp_path) -> None:
    path = tmp_path / "tables.json"
    repository = JsonTableRepository(path)
    repository.create("legacy-agent", "Q", [_seed("p1")])
    payload = json.loads(path.read_text(encoding="utf-8"))
    for snapshot in payload["tables"]["legacy-agent"]["states"]:
        snapshot.pop("agent", None)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    restored = JsonTableRepository(path)
    assert restored.get("legacy-agent").agent.agent_id == "roundtable-agent"
