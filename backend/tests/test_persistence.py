import pytest

from app.api.repository import JsonTableRepository
from app.demo import SCENARIOS, flagship_participants
from app.domain import HumanTurn, SafetyLevel
from app.orchestrator import decide_intervention, enforce_safety, evaluate_safety


def test_json_repository_recovers_snapshots_messages_and_safety_state(tmp_path) -> None:
    path = tmp_path / "nested" / "table.json"
    repository = JsonTableRepository(path)
    repository.create("persisted", "Q", flagship_participants)
    for turn in SCENARIOS["flagship"][:2]:
        repository.append_turn("persisted", turn)
    repository.append_safety_state(
        "persisted", enforce_safety(repository.get("persisted"), evaluate_safety("我会威胁你。", 3))
    )
    assert len(repository.turns("persisted")) == 2

    restored = JsonTableRepository(path)
    assert [state.version for state in restored.replay("persisted")] == [0, 1, 2, 3]
    assert restored.turns("persisted") == SCENARIOS["flagship"][:2]
    assert restored.get("persisted").conversation.safety_level is SafetyLevel.CRITICAL


def test_json_repository_returns_isolated_models_after_restart(tmp_path) -> None:
    path = tmp_path / "table.json"
    repository = JsonTableRepository(path)
    repository.create("copies", "Q", flagship_participants)
    repository.append_turn("copies", HumanTurn(turn_id=1, participant_id="architect", text="原始消息"))
    restored = JsonTableRepository(path)
    restored.get("copies").core_question = "篡改"
    restored.replay("copies")[0].core_question = "篡改"
    restored.turns("copies")[0].text = "篡改"
    assert restored.get("copies").core_question == "Q"
    assert restored.replay("copies")[0].core_question == "Q"
    assert restored.turns("copies")[0].text == "原始消息"


def test_json_repository_rejects_corrupt_files(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid persistence file"):
        JsonTableRepository(path)


def test_flagship_replay_is_stable_across_ten_persisted_runs(tmp_path) -> None:
    histories = []
    for index in range(10):
        repository = JsonTableRepository(tmp_path / f"run-{index}.json")
        repository.create("flagship", "AI Agent 真正进入企业，卡住的是技术还是采购？", flagship_participants)
        routes = []
        for turn in SCENARIOS["flagship"]:
            state = repository.append_turn("flagship", turn)
            routes.append((state.version, decide_intervention(state)[1].action.value))
        restored = JsonTableRepository(repository.path)
        histories.append(([state.version for state in restored.replay("flagship")], routes))
    assert histories == [histories[0]] * 10
