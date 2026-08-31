import pytest
from pydantic import ValidationError

from app.demo import SCENARIOS, flagship_participants
from app.domain import Action, DisagreementType, GroundingCard, RouteDecision
from app.domain.schemas import Disagreement
from app.orchestrator import build_initial_state, generate_host_event, observe_turn


QUESTION = "AI Agent 真正进入企业，卡住的是技术还是采购？"


def state_after(name: str):
    state = build_initial_state("host", QUESTION, flagship_participants)
    for turn in SCENARIOS[name]:
        state = observe_turn(state, turn)
    return state


def decision(action: Action, evidence: list[int] | None = None, target: str | None = None):
    return RouteDecision(action=action, evidence_turns=evidence or [1], target_participant_id=target, confidence=.73)


@pytest.mark.parametrize("action", list(Action))
def test_every_action_returns_frontend_event(action: Action) -> None:
    route = decision(action, target="buyer" if action is Action.PASS else None)
    event = generate_host_event(state_after("flagship"), route)
    assert event.state_version == 3 and event.evidence_turns == [1]
    assert isinstance(event.visual_hint, dict) and event.action in Action
    if action is Action.SILENCE:
        assert event.text is None
    else:
        assert event.text and len(event.text) <= 120


def test_pass_explains_why_the_target_is_invited() -> None:
    state = state_after("pass")
    event = generate_host_event(state, decision(Action.PASS, [1], "buyer"))
    assert event.action is Action.PASS
    assert all(part in event.text for part in ("林青", "企业采购负责人", "供应商采购"))
    assert "作为AI" not in event.text


@pytest.mark.parametrize("action", [Action.PASS, Action.REFRAME])
def test_unknown_target_fails_safe(action: Action) -> None:
    event = generate_host_event(state_after("flagship"), decision(action, [1], "ghost"))
    assert (event.action, event.target_participant_id, event.text) == (Action.SILENCE, None, None)
    assert event.visual_hint["kind"] == "silence" and event.evidence_turns == [1]


def test_reframe_names_the_structure_and_passes_to_target() -> None:
    state = state_after("flagship")
    state.disagreements.insert(0, Disagreement(text="事实冲突", evidence_turns=[3], disagreement_type=DisagreementType.FACT_CONFLICT, participant_ids=["architect", "security"]))
    event = generate_host_event(state, decision(Action.REFRAME, [1, 2], "buyer"))
    assert event.action is Action.REFRAME
    assert all(part in event.text for part in ("技术", "采购", "同一层", "林青"))
    assert event.visual_hint["show_structure"] is True


@pytest.mark.parametrize("kind", ["natural", "pass", "experience"])
def test_probe_asks_for_example_reason_and_boundary(kind: str) -> None:
    state = state_after(kind)
    event = generate_host_event(state, decision(Action.PROBE, [1]))
    assert all(part in event.text for part in ("具体例子", "原因", "边界"))


def test_grounding_card_is_the_only_source_content() -> None:
    state = state_after("natural")
    card = GroundingCard(title="采购流程研究", excerpt="试点与正式采购由不同责任链承接。", source_ref="zhihu:answer:42")
    event = generate_host_event(state, decision(Action.GROUND, [1, 2]), card)
    assert event.action is Action.GROUND
    assert all(part in event.text for part in (card.title, card.excerpt, card.source_ref))
    assert event.visual_hint["source_ref"] == card.source_ref


def test_ground_without_card_falls_back_to_probe_without_inventing_source() -> None:
    event = generate_host_event(state_after("natural"), decision(Action.GROUND, [1], "buyer"))
    assert event.action is Action.PROBE and event.text
    assert event.visual_hint["fallback_from"] == "GROUND"
    assert "来源" not in event.text and event.target_participant_id is None
    assert event.visual_hint["focus"] == ["question"]


def test_grounding_card_rejects_empty_source_fields() -> None:
    with pytest.raises(ValidationError):
        GroundingCard(title="", excerpt="内容", source_ref="ref")
    with pytest.raises(ValidationError):
        GroundingCard(title="标题", excerpt="内容", source_ref="")


def test_close_keeps_original_question_and_next_question() -> None:
    state = state_after("flagship")
    event = generate_host_event(state, decision(Action.CLOSE, [1, 2]))
    assert "原问题" in event.text and state.current_subquestion in event.text
    assert event.visual_hint["focus"] == ["summary", "next_question"]


def test_silence_does_not_force_host_text() -> None:
    event = generate_host_event(state_after("natural"), RouteDecision())
    assert event.action is Action.SILENCE and event.text is None
    assert event.visual_hint["kind"] == "silence"


def test_host_text_is_bounded_and_has_no_system_jargon() -> None:
    state = state_after("natural").model_copy(deep=True)
    state.core_question = "检测到" + "很长的问题" * 50
    event = generate_host_event(state, decision(Action.PROBE, [1]))
    assert len(event.text) <= 120
    assert not any(term in event.text for term in ("检测到", "根据分析", "作为AI"))


@pytest.mark.parametrize("action", [Action.PASS, Action.PROBE, Action.REFRAME, Action.GROUND, Action.CLOSE])
def test_non_silence_event_aligns_with_route_metadata(action: Action) -> None:
    target = "buyer" if action is Action.PASS else None
    event = generate_host_event(state_after("flagship"), decision(action, [2, 3], target))
    assert event.evidence_turns == [2, 3] and event.confidence == .73 and event.state_version == 3
