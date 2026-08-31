import json

import pytest

from app.api.repository import JsonTableRepository
from app.demo import SCENARIOS, flagship_participants
from app.domain import Action, GroundingCard, HumanTurn, InterventionRecord, SafetyLevel
from app.domain.schemas import EvidenceStatement, TokenUsage
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


def test_json_repository_persists_trusted_grounding_card_and_consumes_atomically(tmp_path) -> None:
    path = tmp_path / "grounding.json"
    repository = JsonTableRepository(path)
    repository.create("grounded", "Q", flagship_participants)
    card = GroundingCard(title="采购流程", excerpt="试点和正式采购责任链不同。", source_ref="demo:42")
    repository.set_trusted_grounding_card("grounded", card)

    restored = JsonTableRepository(path)
    assert restored.take_trusted_grounding_card("grounded") == card
    assert JsonTableRepository(path).take_trusted_grounding_card("grounded") is None


def test_json_repository_loads_legacy_snapshot_without_grounding_cards(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    repository = JsonTableRepository(path)
    repository.create("legacy", "Q", flagship_participants)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("trusted_grounding_cards")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    restored = JsonTableRepository(path)
    assert restored.get("legacy").table_id == "legacy"
    assert restored.take_trusted_grounding_card("legacy") is None


def test_json_repository_persists_intervention_audit_records(tmp_path) -> None:
    path = tmp_path / "audit.json"
    repository = JsonTableRepository(path)
    repository.create("audit", "Q", flagship_participants)
    repository.append_turn("audit", HumanTurn(turn_id=1, participant_id="architect", text="我亲历过试点。"))
    record = InterventionRecord(
        action=Action.PROBE,
        target_participant_id="architect",
        text="能补充一条现场证据吗？",
        visual_hint={"kind": "probe"},
        evidence_turns=[1],
        state_version=1,
        confidence=.8,
        intervention_id="audit:intervention:1",
        table_id="audit",
        reasons_to_speak=[EvidenceStatement(text="有现场证据", evidence_turns=[1])],
        latency_ms=3,
        model="test",
        token_usage=TokenUsage(input_tokens=2, output_tokens=4),
    )
    repository.append_intervention_record("audit", record)
    assert repository.interventions("audit") == [record]
    assert JsonTableRepository(path).interventions("audit") == [record]


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
