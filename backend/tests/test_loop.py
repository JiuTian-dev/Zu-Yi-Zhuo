import pytest

from app.demo import SCENARIOS, flagship_participants
from app.domain import Action, HumanTurn, RouteDecision
from app.orchestrator import build_initial_state, decide_intervention, observe_turn, record_intervention

QUESTION = "AI Agent 真正进入企业，卡住的是技术还是采购？"


def replay(name: str):
    state = build_initial_state("loop", QUESTION, flagship_participants)
    for turn in SCENARIOS[name]:
        state = observe_turn(state, turn)
    return state


def test_record_intervention_is_immutable_and_writes_cooldown_fields() -> None:
    previous = replay("flagship")
    before = previous.model_dump()
    _, decision = decide_intervention(previous)
    recorded = record_intervention(previous, decision, "agent-4")

    assert previous.model_dump() == before
    assert recorded.version == previous.version + 1
    assert (recorded.intervention.last_action, recorded.intervention.last_agent_turn_id) == (Action.REFRAME, "agent-4")
    assert recorded.intervention.recommended_action is Action.SILENCE
    assert recorded.intervention.human_turns_since_last_intervention == 0
    assert not recorded.participants["buyer"].good_pass_opportunity


@pytest.mark.parametrize(("decision", "turn_id", "message"), [
    (RouteDecision(), "agent-1", "SILENCE"),
    (RouteDecision(action=Action.PROBE, evidence_turns=[1]), "", "agent_turn_id"),
])
def test_fake_interventions_are_rejected(decision, turn_id: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        record_intervention(replay("natural"), decision, turn_id)


def test_record_then_one_and_two_human_turns_respect_cooldown() -> None:
    state = replay("flagship")
    state = record_intervention(state, decide_intervention(state)[1], "agent-4")
    state = observe_turn(state, HumanTurn(turn_id=4, participant_id="founder", text="采购责任仍需澄清。"))
    assert decide_intervention(state)[1].action is Action.SILENCE
    state = observe_turn(state, HumanTurn(turn_id=5, participant_id="product", text="预算责任与技术验收要分层。"))
    assert decide_intervention(state)[1].action is Action.REFRAME


def test_pass_scenario_reaches_pass_without_layer_mismatch() -> None:
    state = replay("pass")
    gate, decision = decide_intervention(state)
    assert not state.disagreements and gate.should_speak
    assert (decision.action, decision.target_participant_id) == (Action.PASS, "buyer")
    assert replay("natural").participants["buyer"].good_pass_opportunity is False
