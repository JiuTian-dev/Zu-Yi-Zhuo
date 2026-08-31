import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.api.repository import JsonTableRepository
from app.demo import SCENARIOS, flagship_participants
from app.domain import Action, FollowUpOutcome, GroundingCard, HumanTurn, InterventionRecord, SafetyLevel
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


def test_json_repository_deduplicates_message_ids_across_restart(tmp_path) -> None:
    path = tmp_path / "idempotency.json"
    repository = JsonTableRepository(path)
    repository.create("idempotent", "Q", flagship_participants)

    first, created = repository.append_message_once(
        "idempotent", "architect", "我亲历过试点。", "msg-1"
    )
    assert created is True
    duplicate, created = repository.append_message_once(
        "idempotent", "architect", "我亲历过试点。", "msg-1"
    )
    assert created is False
    assert duplicate.version == first.version

    restored = JsonTableRepository(path)
    duplicate_after_restart, created = restored.append_message_once(
        "idempotent", "architect", "我亲历过试点。", "msg-1"
    )
    assert created is False
    assert duplicate_after_restart.version == first.version
    with pytest.raises(ValueError, match="different message"):
        restored.append_message_once("idempotent", "architect", "换一条内容", "msg-1")


def test_json_repository_persists_soft_expiry_and_keeps_close_available(tmp_path) -> None:
    path = tmp_path / "soft-expiry.json"
    repository = JsonTableRepository(path)
    repository.create("stale", "Q", [flagship_participants[0]])
    expired = repository.soft_expire_table("stale", "问题热度已下降")
    assert expired.version == 1
    assert expired.conversation.soft_expired is True
    assert repository.list_tables() == []

    restored = JsonTableRepository(path)
    assert restored.get("stale").conversation.soft_expired is True
    assert restored.get("stale").conversation.soft_expiry_reason == "问题热度已下降"
    assert [state.version for state in restored.replay("stale")] == [0, 1]
    with pytest.raises(ValueError, match="soft-expired"):
        restored.append_turn(
            "stale", HumanTurn(turn_id=1, participant_id="architect", text="不应继续写入")
        )
    closed = restored.close_table("stale")
    assert closed.conversation.closed is True
    assert JsonTableRepository(path).get("stale").conversation.closed is True


def test_json_repository_enforces_five_seat_capacity(tmp_path) -> None:
    repository = JsonTableRepository(tmp_path / "capacity.json")
    repository.create("capacity", "Q", flagship_participants)

    with pytest.raises(ValueError, match="cannot exceed 5"):
        repository.add_participant(
            "capacity", flagship_participants[0].model_copy(update={"participant_id": "extra"})
        )

    restored = JsonTableRepository(repository.path)
    assert len(restored.get("capacity").participants) == 5


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


def test_json_repository_persists_invitation_state_and_acceptance(tmp_path) -> None:
    path = tmp_path / "invitations.json"
    repository = JsonTableRepository(path)
    repository.create("invite", "Q", [flagship_participants[0]])
    invitation = repository.create_invitation(
        "invite", "architect", flagship_participants[1], "需要产品视角"
    )

    restored = JsonTableRepository(path)
    assert restored.invitations("invite") == [invitation]
    accepted, state = restored.respond_invitation(
        "invite", invitation.invitation_id, "product", True
    )
    assert accepted.status.value == "accepted"
    assert state is not None and state.version == 1

    reloaded = JsonTableRepository(path)
    assert reloaded.get("invite").participants["product"].display_name == "周宁"
    assert reloaded.invitations("invite")[0].status.value == "accepted"


def test_follow_up_outcome_is_persisted_and_upserted_after_close(tmp_path) -> None:
    path = tmp_path / "follow-ups.json"
    repository = JsonTableRepository(path)
    repository.create("echo", "Q", [flagship_participants[0]])
    repository.append_turn("echo", HumanTurn(turn_id=1, participant_id="architect", text="我会先做一次小范围试点。"))
    repository.close_table("echo")

    outcome = FollowUpOutcome(
        table_id="echo", follow_up_index=0, participant_id="architect",
        status="in_progress", note="已经找到试点对象",
    )
    assert repository.record_follow_up_outcome(outcome) == outcome
    updated = outcome.model_copy(update={"status": "completed", "note": "已完成第一轮验证"})
    assert repository.record_follow_up_outcome(updated) == updated

    restored = JsonTableRepository(path)
    assert restored.follow_up_outcomes("echo") == [updated]


def test_follow_up_outcome_rejects_open_table_and_unknown_participant(tmp_path) -> None:
    repository = JsonTableRepository(tmp_path / "follow-ups-invalid.json")
    repository.create("open", "Q", [flagship_participants[0]])
    outcome = FollowUpOutcome(
        table_id="open", follow_up_index=0, participant_id="architect", status="completed",
    )
    with pytest.raises(ValueError, match="closed"):
        repository.record_follow_up_outcome(outcome)
    repository.close_table("open")
    with pytest.raises(ValueError, match="unknown participant"):
        repository.record_follow_up_outcome(outcome.model_copy(update={"participant_id": "ghost"}))


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


def test_in_memory_repository_serializes_competing_consent_writes() -> None:
    from app.api.repository import InMemoryTableRepository

    repository = InMemoryTableRepository()
    repository.create("concurrent", "Q", [
        flagship_participants[0].model_copy(update={"participant_id": "p1"}),
        flagship_participants[1].model_copy(update={"participant_id": "p2"}),
    ])
    barrier = Barrier(2)

    def share(participant_id: str) -> None:
        barrier.wait()
        repository.set_profile_consent("concurrent", participant_id, True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(share, ("p1", "p2")))

    state = repository.get("concurrent")
    assert state.version == 2
    assert all(person.profile_shared for person in state.participants.values())


def test_in_memory_repository_deduplicates_competing_message_retries() -> None:
    from app.api.repository import InMemoryTableRepository

    repository = InMemoryTableRepository()
    repository.create("concurrent-message", "Q", flagship_participants)
    barrier = Barrier(2)

    def submit() -> tuple[int, bool]:
        barrier.wait()
        state, created = repository.append_message_once(
            "concurrent-message", "architect", "我亲历过试点。", "same-id"
        )
        return state.version, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))

    assert sorted(results) == [(1, False), (1, True)]
    assert len(repository.turns("concurrent-message")) == 1
    assert repository.get("concurrent-message").version == 1


def test_intervention_bundle_rejects_invalid_audit_without_committing_state() -> None:
    from app.api.repository import InMemoryTableRepository

    repository = InMemoryTableRepository()
    repository.create("bundle", "Q", flagship_participants)
    next_state = repository.get("bundle").model_copy(update={"version": 1})
    invalid_record = InterventionRecord(
        action=Action.PROBE,
        text="请补充一条现场证据。",
        visual_hint={"kind": "probe"},
        evidence_turns=[1],
        state_version=2,
        confidence=.8,
        intervention_id="bundle:intervention:2",
        table_id="bundle",
        reasons_to_speak=[EvidenceStatement(text="有现场证据", evidence_turns=[1])],
        latency_ms=0,
        model="test",
        token_usage=TokenUsage(input_tokens=0, output_tokens=0),
    )

    with pytest.raises(ValueError, match="new table state"):
        repository.append_intervention_bundle("bundle", next_state, invalid_record)

    assert repository.get("bundle").version == 0
    assert repository.interventions("bundle") == []

    with pytest.raises(ValueError, match="SILENCE"):
        repository.append_intervention_record(
            "bundle",
            invalid_record.model_copy(update={
                "action": Action.SILENCE,
                "state_version": 0,
                "intervention_id": "bundle:intervention:silence",
            }),
        )


def test_json_intervention_bundle_recovers_state_and_audit_together(tmp_path) -> None:
    path = tmp_path / "bundle.json"
    repository = JsonTableRepository(path)
    repository.create("bundle", "Q", flagship_participants)
    next_state = repository.get("bundle").model_copy(update={"version": 1})
    record = InterventionRecord(
        action=Action.PROBE,
        text="请补充一条现场证据。",
        visual_hint={"kind": "probe"},
        evidence_turns=[1],
        state_version=1,
        confidence=.8,
        intervention_id="bundle:intervention:1",
        table_id="bundle",
        reasons_to_speak=[EvidenceStatement(text="有现场证据", evidence_turns=[1])],
        latency_ms=0,
        model="test",
        token_usage=TokenUsage(input_tokens=0, output_tokens=0),
    )

    repository.append_intervention_bundle("bundle", next_state, record)
    restored = JsonTableRepository(path)
    assert restored.get("bundle").version == 1
    assert restored.interventions("bundle") == [record]
