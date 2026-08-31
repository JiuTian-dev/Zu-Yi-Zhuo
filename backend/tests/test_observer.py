import json
import subprocess
import sys

import pytest

from app.demo import SCENARIOS, flagship_participants
from app.domain import Action, DisagreementType, HumanTurn
from app.orchestrator import build_initial_state, observe_turn

QUESTION = "AI Agent 真正进入企业，卡住的是技术还是采购？"

def initial():
    return build_initial_state("t-1", QUESTION, flagship_participants)

def replay(name: str):
    state = initial()
    for turn in SCENARIOS[name]:
        state = observe_turn(state, turn)
    return state

def test_five_flagship_roles_are_seeded() -> None:
    state = initial()
    assert len(state.participants) == 5
    assert set(state.participants) == {p.participant_id for p in flagship_participants}
    assert all(p.declared_position and p.unused_relevant_experience for p in state.participants.values())

def test_initial_state_defaults_to_silence() -> None:
    state = initial()
    assert (state.version, state.phase.value, state.intervention.recommended_action) == (0, "opening", Action.SILENCE)

def test_turn_returns_new_snapshot_and_increments_version() -> None:
    before = initial(); payload = before.model_dump()
    after = observe_turn(before, SCENARIOS["natural"][0])
    assert after is not before and after.version == before.version + 1
    assert before.model_dump() == payload

def test_natural_follow_up_remains_silent() -> None:
    state = replay("natural")
    assert state.phase.value == "explore" and state.intervention.recommended_action is Action.SILENCE
    assert state.intervention.reasons_to_stay_silent[0].evidence_turns == [2]
    assert state.intervention.reasons_to_stay_silent[0].text == "讨论仍在自然推进"

def test_speaker_engagement_and_last_spoke_update() -> None:
    state = observe_turn(initial(), SCENARIOS["natural"][0])
    speaker = state.participants["founder"]
    assert (speaker.engagement.value, speaker.last_spoke_turn) == ("high", 1)
    assert state.participants["architect"].last_spoke_turn is None

def test_unknown_participant_is_rejected_without_mutation() -> None:
    state = initial(); payload = state.model_dump()
    with pytest.raises(ValueError, match="unknown participant"):
        observe_turn(state, HumanTurn(turn_id=1, participant_id="ghost", text="hello"))
    assert state.model_dump() == payload

def test_duplicate_or_out_of_order_turn_is_rejected_immutably() -> None:
    state = observe_turn(initial(), SCENARIOS["natural"][0]); payload = state.model_dump()
    with pytest.raises(ValueError, match="strictly increasing"):
        observe_turn(state, HumanTurn(turn_id=1, participant_id="product", text="重复 turn"))
    assert state.model_dump() == payload

def test_flagship_detects_layer_mismatch() -> None:
    state = replay("flagship")
    mismatch = next(item for item in state.disagreements if item.disagreement_type is DisagreementType.LAYER_MISMATCH)
    assert mismatch.evidence_turns == [1, 2]
    assert set(mismatch.participant_ids) == {"architect", "product"}
    assert state.current_subquestion and state.open_loops[0].priority.value == "high"
    assert state.conversation.state == "layer_mismatch surfaced"
    assert state.conversation.most_promising_thread.text == "采购决策链"

def test_unheard_procurement_expert_is_pass_opportunity() -> None:
    state = replay("flagship")
    assert state.intervention.recommended_action is Action.PASS
    assert state.participants["buyer"].good_pass_opportunity
    assert state.intervention.reasons_to_speak[0].evidence_turns == [1, 2]

def test_seed_source_is_not_fabricated_as_turn_evidence() -> None:
    state = replay("flagship")
    evidence = state.intervention.reasons_to_speak[0].evidence_turns
    assert all(isinstance(turn_id, int) and turn_id > 0 for turn_id in evidence)
    assert "seed:buyer:procurement" not in evidence

def test_insights_and_contributions_are_bounded() -> None:
    state = initial()
    for turn_id in range(1, 13):
        state = observe_turn(state, HumanTurn(turn_id=turn_id, participant_id="founder", text=f"试点案例 {turn_id}"))
    assert len(state.new_insights) == 8
    assert len(state.participants["founder"].key_contributions) == 3

def test_pass_opportunity_clears_when_expert_speaks() -> None:
    state = observe_turn(observe_turn(initial(), SCENARIOS["flagship"][0]), SCENARIOS["flagship"][1])
    assert state.participants["buyer"].good_pass_opportunity
    state = observe_turn(state, HumanTurn(turn_id=3, participant_id="buyer", text="采购要看预算和责任。"))
    assert not state.participants["buyer"].good_pass_opportunity

def test_contributed_seed_experience_is_consumed() -> None:
    buyer = replay("experience").participants["buyer"]
    assert buyer.unused_relevant_experience == [] and not buyer.good_pass_opportunity

@pytest.mark.parametrize("scenario", SCENARIOS)
def test_all_scenarios_replay_to_valid_snapshots(scenario: str) -> None:
    state = replay(scenario)
    assert state.version == len(SCENARIOS[scenario])
    assert state.model_validate(state.model_dump()) == state

@pytest.mark.parametrize(("scenario", "action", "target"), [
    ("flagship", "REFRAME", "buyer"),
    ("natural", "SILENCE", None),
    ("experience", "REFRAME", None),
    ("pass", "PASS", "buyer"),
])
def test_cli_outputs_gate_and_route_for_every_scenario(scenario: str, action: str, target: str | None) -> None:
    result = subprocess.run([sys.executable, "-m", "app.cli.replay", "--scenario", scenario],
                            check=True, capture_output=True, text=True)
    snapshots = json.loads(result.stdout); final = snapshots[-1]
    assert len(snapshots) == len(SCENARIOS[scenario]) + 1
    assert all({"observer_recommended_action", "gate", "route"} <= snapshot.keys() for snapshot in snapshots)
    assert {"action", "target_participant_id", "evidence_turns", "confidence"} <= final["route"].keys()
    assert (final["route"]["action"], final["route"]["target_participant_id"]) == (action, target)
    if scenario == "flagship":
        assert (final["version"], final["phase"], final["observer_recommended_action"]) == (3, "tension", "PASS")
