"""Deterministic demo Observer fallback; replaceable by an LLM provider later."""

from collections.abc import Sequence

from app.domain import Action, DisagreementType, HumanTurn, Level, ParticipantSeed, Phase, SafetyLevel, TableState
from app.domain.schemas import ConversationState, Disagreement, EvidenceStatement, InterventionState, OpenLoop, ParticipantState

TECH = ("技术", "模型", "精度", "延迟", "架构")
BUYING = ("采购", "预算", "招标", "责任", "供应商")
CONTRIBUTION = ("亲历", "数据", "试点", "案例", "经验")

def build_initial_state(table_id: str, core_question: str, participants: Sequence[ParticipantSeed]) -> TableState:
    mapped = {seed.participant_id: ParticipantState(
        participant_id=seed.participant_id, display_name=seed.display_name, role=seed.role, declared_position=seed.declared_position,
        unused_relevant_experience=seed.relevant_experience, engagement=Level.LOW,
    ) for seed in participants}
    if len(mapped) != len(participants):
        raise ValueError("participant_id must be unique")
    return TableState(
        table_id=table_id, version=0, core_question=core_question, phase=Phase.OPENING,
        momentum=Level.LOW, close_readiness=Level.LOW, participants=mapped,
        conversation=ConversationState(state="active", safety_level=SafetyLevel.NORMAL),
        intervention=InterventionState(confidence=1.0),
    )

def _layer(text: str) -> str | None:
    if any(word in text for word in TECH): return "tech"
    if any(word in text for word in BUYING): return "buying"
    return None

def observe_turn(previous: TableState, turn: HumanTurn) -> TableState:
    """Return a fresh snapshot after one committed human turn."""
    if turn.participant_id not in previous.participants:
        raise ValueError(f"unknown participant: {turn.participant_id}")
    latest_turn = max((p.last_spoke_turn or 0 for p in previous.participants.values()), default=0)
    if turn.turn_id <= latest_turn:
        raise ValueError("turn_id must be strictly increasing")
    state = previous.model_copy(deep=True)
    state.version += 1
    speaker = state.participants[turn.participant_id]
    statement = EvidenceStatement(text=turn.text, evidence_turns=[turn.turn_id])
    speaker.current_position = statement
    speaker.last_spoke_turn = turn.turn_id
    speaker.engagement = Level.HIGH
    speaker.good_pass_opportunity = False
    if any(word in turn.text for word in CONTRIBUTION):
        speaker.key_contributions = (speaker.key_contributions + [statement])[-3:]
        speaker.unused_relevant_experience = []
        state.new_insights = (state.new_insights + [statement])[-8:]
    state.phase = Phase.EXPLORE
    state.momentum = Level.MEDIUM if state.version < 3 else Level.HIGH
    state.intervention = InterventionState(
        recommended_action=Action.SILENCE, confidence=.9,
        last_action=previous.intervention.last_action,
        last_agent_turn_id=previous.intervention.last_agent_turn_id,
        human_turns_since_last_intervention=previous.intervention.human_turns_since_last_intervention + 1,
        reasons_to_stay_silent=[EvidenceStatement(text="讨论仍在自然推进", evidence_turns=[turn.turn_id])],
    )
    positions = [(pid, p.current_position) for pid, p in state.participants.items() if p.current_position]
    tech = next(((pid, item) for pid, item in positions if _layer(item.text) == "tech"), None)
    buying = next(((pid, item) for pid, item in positions if _layer(item.text) == "buying"), None)
    if tech and buying:
        evidence = sorted(set(tech[1].evidence_turns + buying[1].evidence_turns))
        disagreement = Disagreement(text="讨论同时落在技术实现层与采购决策层", evidence_turns=evidence,
                                    disagreement_type=DisagreementType.LAYER_MISMATCH,
                                    participant_ids=[tech[0], buying[0]])
        state.disagreements = [item for item in state.disagreements if item.disagreement_type != DisagreementType.LAYER_MISMATCH] + [disagreement]
        state.phase = Phase.TENSION
        state.current_subquestion = "采购决策链如何影响技术进入企业？"
        state.open_loops = [OpenLoop(question=state.current_subquestion, priority=Level.HIGH, evidence_turns=evidence)]
        state.conversation.state = "layer_mismatch surfaced"
        state.conversation.most_promising_thread = EvidenceStatement(text="采购决策链", evidence_turns=evidence)
        target = next((p for p in state.participants.values()
                       if p.last_spoke_turn is None and p.unused_relevant_experience and
                       ("采购" in p.role or any("采购" in item.text for item in p.unused_relevant_experience))), None)
        if target:
            target.good_pass_opportunity = True
            state.intervention = InterventionState(reasons_to_speak=[disagreement], recommended_action=Action.PASS,
                confidence=.85, last_action=previous.intervention.last_action,
                last_agent_turn_id=previous.intervention.last_agent_turn_id,
                human_turns_since_last_intervention=previous.intervention.human_turns_since_last_intervention + 1)
    return TableState.model_validate(state.model_dump())
