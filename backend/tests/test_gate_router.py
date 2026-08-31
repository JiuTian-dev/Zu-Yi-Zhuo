import pytest

from app.demo import SCENARIOS, flagship_participants
from app.domain import Action, DisagreementType, Level, Phase, SafetyLevel
from app.domain.schemas import Disagreement, EvidenceStatement, OpenLoop
from app.orchestrator import build_initial_state, evaluate_gate, observe_turn, route

QUESTION = "AI Agent 真正进入企业，卡住的是技术还是采购？"


def _state(kind: str):
    state = build_initial_state("golden", QUESTION, flagship_participants).model_copy(deep=True)
    number = int(kind.rsplit("-", 1)[-1]) if kind.rsplit("-", 1)[-1].isdigit() else 1
    evidence = [number + 1]
    if kind.startswith("cooldown"):
        state.intervention.last_action = Action.PROBE
        state.intervention.human_turns_since_last_intervention = number
        state.disagreements = [Disagreement(text="层次不同", evidence_turns=evidence,
            disagreement_type=DisagreementType.LAYER_MISMATCH, participant_ids=["architect", "product"])]
    elif kind.startswith("natural"):
        state.phase = {"natural-opening": Phase.OPENING, "natural-explore": Phase.EXPLORE,
                       "natural-deepen": Phase.DEEPEN}.get(kind, Phase.EXPLORE)
        if "loop" in kind:
            priority = Level.LOW if "low" in kind else Level.MEDIUM
            state.open_loops = [OpenLoop(question="继续吗", priority=priority, evidence_turns=evidence)]
    elif kind.startswith(("layer", "definition")):
        mismatch = DisagreementType.LAYER_MISMATCH if kind.startswith("layer") else DisagreementType.DEFINITION_MISMATCH
        state.disagreements = [Disagreement(text="需要重构", evidence_turns=evidence,
            disagreement_type=mismatch, participant_ids=["architect", "product"])]
        if "target" in kind:
            state.participants["buyer"].good_pass_opportunity = True
    elif kind.startswith("fact"):
        state.disagreements = [Disagreement(text="事实冲突", evidence_turns=evidence,
            disagreement_type=DisagreementType.FACT_CONFLICT, participant_ids=["founder", "architect"])]
    elif kind.startswith("pass"):
        state.participants["buyer"].good_pass_opportunity = True
        state.intervention.reasons_to_speak = [EvidenceStatement(text="亲历者尚未参与", evidence_turns=evidence)]
    elif kind.startswith("probe"):
        state.open_loops = [OpenLoop(question="关键问题", priority=Level.HIGH, evidence_turns=evidence)]
    elif kind.startswith("close"):
        state.close_readiness = Level.HIGH
        state.phase = Phase.CLOSE if "phase" in kind else Phase.EXPLORE
        state.momentum = Level.LOW
        state.new_insights = [EvidenceStatement(text="信息增量下降", evidence_turns=evidence)]
    elif kind.startswith("safety"):
        state.conversation.safety_level = SafetyLevel.CRITICAL
        state.conversation.risk_flags = [EvidenceStatement(text="安全风险", evidence_turns=evidence)]
        state.intervention.last_action = Action.PROBE
        state.intervention.human_turns_since_last_intervention = 0
    return state.model_validate(state.model_dump())


GOLDEN = [
    ("cooldown-0", Action.SILENCE), ("cooldown-1", Action.SILENCE),
    ("cooldown-2", Action.REFRAME),
    ("natural-opening", Action.SILENCE), ("natural-explore", Action.SILENCE),
    ("natural-deepen", Action.SILENCE), ("natural-low-loop", Action.SILENCE),
    ("natural-medium-loop", Action.SILENCE),
    ("layer-1", Action.REFRAME), ("layer-2", Action.REFRAME),
    ("layer-target-3", Action.REFRAME), ("definition-4", Action.REFRAME),
    ("fact-1", Action.GROUND), ("fact-2", Action.GROUND), ("fact-3", Action.GROUND),
    ("pass-1", Action.PASS), ("pass-2", Action.PASS), ("pass-3", Action.PASS),
    ("probe-1", Action.PROBE), ("probe-2", Action.PROBE), ("probe-3", Action.PROBE),
    ("close-phase-1", Action.CLOSE), ("close-low-2", Action.CLOSE), ("close-low-3", Action.CLOSE),
    ("safety-1", Action.REFRAME), ("safety-2", Action.REFRAME),
]


@pytest.mark.parametrize(("kind", "expected"), GOLDEN)
def test_golden_routes(kind: str, expected: Action) -> None:
    state = _state(kind)
    assert route(state, evaluate_gate(state)).action is expected


def test_golden_action_accuracy_is_at_least_75_percent() -> None:
    correct = sum(route(state := _state(kind), evaluate_gate(state)).action is expected for kind, expected in GOLDEN)
    assert len(GOLDEN) == 26 and correct / len(GOLDEN) >= .75


def test_flagship_reframes_then_targets_buyer() -> None:
    state = build_initial_state("flagship", QUESTION, flagship_participants)
    for turn in SCENARIOS["flagship"]:
        state = observe_turn(state, turn)
    decision = route(state, evaluate_gate(state))
    assert (decision.action, decision.target_participant_id) == (Action.REFRAME, "buyer")


def test_safety_override_beats_cooldown_and_is_explicit() -> None:
    state = _state("safety-1")
    gate = evaluate_gate(state)
    assert gate.should_speak and gate.safety_override and gate.reasons_to_speak and gate.confidence == .99
    assert route(state, gate).action is Action.REFRAME


def test_critical_safety_without_risk_evidence_is_rejected() -> None:
    state = _state("natural-explore")
    payload = state.model_dump()
    payload["conversation"]["safety_level"] = "critical"
    with pytest.raises(ValueError, match="critical safety requires risk_flags"):
        state.model_validate(payload)


@pytest.mark.parametrize("turns", [0, 1])
def test_cooldown_reason_is_observable(turns: int) -> None:
    gate = evaluate_gate(_state(f"cooldown-{turns}"))
    assert not gate.should_speak and gate.reasons_to_stay_silent == ["cooldown requires two human turns"]


def test_candidate_reason_and_cooldown_boundary_are_observable() -> None:
    state = _state("cooldown-2")
    gate = evaluate_gate(state)
    assert gate.reasons_to_speak == ["high-value intervention candidate exists"] and gate.confidence == .9
    assert route(state, gate).action is Action.REFRAME


@pytest.mark.parametrize("misleading", [Action.CLOSE, Action.PASS])
def test_observer_candidate_does_not_control_router(misleading: Action) -> None:
    state = _state("natural-explore")
    state.intervention.recommended_action = misleading
    gate = evaluate_gate(state)
    assert route(state, gate).action is Action.SILENCE
    assert gate.reasons_to_stay_silent == ["natural progression has no new intervention value"]


def test_evidence_is_deduplicated_without_mutating_state() -> None:
    state = _state("layer-1")
    state.disagreements.append(state.disagreements[0].model_copy(deep=True))
    before = state.model_dump()
    decision = route(state, evaluate_gate(state))
    assert decision.evidence_turns == [2] and state.model_dump() == before


def test_target_only_comes_from_pass_opportunity() -> None:
    state = _state("layer-1")
    assert route(state, evaluate_gate(state)).target_participant_id is None
    state = _state("layer-target-3")
    assert route(state, evaluate_gate(state)).target_participant_id == "buyer"
