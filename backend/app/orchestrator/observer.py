"""Deterministic demo Observer fallback; replaceable by an LLM provider later."""

from collections.abc import Sequence

from app.domain import Action, DisagreementType, HumanTurn, Level, ParticipantSeed, Phase, SafetyLevel, TableState
from app.domain.schemas import ConversationState, Disagreement, EvidenceStatement, InterventionState, OpenLoop, ParticipantState
from .close import refresh_close_readiness

TECH = ("技术", "模型", "精度", "延迟", "架构")
BUYING = ("采购", "预算", "招标", "责任", "供应商")
CONTRIBUTION = ("亲历", "数据", "试点", "案例", "经验")
# Fact conflicts are intentionally narrower than ordinary disagreement.  A
# topic must be explicit and one side must use an unambiguous polarity marker;
# this keeps normal opinion/layer differences on their existing paths.
FACT_TOPICS = (
    "安全审查", "模型精度", "正式生产", "责任归属", "权限边界",
    "采购", "预算", "招标", "责任", "精度", "延迟", "试点", "验收",
)
FACT_NEGATIVE = ("不需要", "无需", "不能", "无法", "没有", "不存在", "不是", "尚未")
FACT_POSITIVE = ("需要", "可以", "能够", "已经", "支持", "存在", "确实")

def build_initial_state(
    table_id: str,
    core_question: str,
    participants: Sequence[ParticipantSeed],
    origin_table_id: str | None = None,
    origin_signal_ids: Sequence[str] | None = None,
) -> TableState:
    origin_ids = list(origin_signal_ids or [])
    mapped = {seed.participant_id: ParticipantState(
        participant_id=seed.participant_id, display_name=seed.display_name, role=seed.role, declared_position=seed.declared_position,
        unused_relevant_experience=seed.relevant_experience,
        roundtable_invite_preference=seed.roundtable_invite_preference,
        engagement=Level.LOW,
    ) for seed in participants}
    if len(mapped) != len(participants):
        raise ValueError("participant_id must be unique")
    available_signal_ids = {
        signal_id
        for seed in participants
        for signal_id in seed.public_signal_ids
    }
    if any(signal_id not in available_signal_ids for signal_id in origin_ids):
        raise ValueError("origin_signal_ids must reference participant public_signal_ids")
    return TableState(
        table_id=table_id, origin_table_id=origin_table_id,
        origin_signal_ids=origin_ids,
        version=0, core_question=core_question, phase=Phase.OPENING,
        momentum=Level.LOW, close_readiness=Level.LOW, participants=mapped,
        conversation=ConversationState(state="active", safety_level=SafetyLevel.NORMAL),
        intervention=InterventionState(confidence=1.0),
    )

def _layer(text: str) -> str | None:
    if any(word in text for word in TECH): return "tech"
    if any(word in text for word in BUYING): return "buying"
    return None

def _procurement_expert(state: TableState) -> ParticipantState | None:
    return next((p for p in state.participants.values()
                 if p.last_spoke_turn is None and p.unused_relevant_experience and
                 ("采购" in p.role or any("采购" in item.text for item in p.unused_relevant_experience))), None)


def _shared_fact_topic(left: str, right: str) -> str | None:
    return next((topic for topic in FACT_TOPICS if topic in left and topic in right), None)


def _fact_polarity(text: str) -> int | None:
    negative = any(marker in text for marker in FACT_NEGATIVE)
    # Remove negative phrases before checking positives so "不需要" is not
    # misread as both negative and positive because it contains "需要".
    positive_text = text
    for marker in FACT_NEGATIVE:
        positive_text = positive_text.replace(marker, "")
    positive = any(marker in positive_text for marker in FACT_POSITIVE)
    if negative == positive:
        return None
    return -1 if negative else 1


def _fact_conflict(
    state: TableState,
    speaker_id: str,
    statement: EvidenceStatement,
) -> Disagreement | None:
    polarity = _fact_polarity(statement.text)
    if polarity is None:
        return None
    candidates: list[tuple[int, str, str, EvidenceStatement]] = []
    for participant_id, participant in state.participants.items():
        if participant_id == speaker_id or participant.current_position is None:
            continue
        other = participant.current_position
        topic = _shared_fact_topic(statement.text, other.text)
        if topic is None or _fact_polarity(other.text) != -polarity:
            continue
        candidates.append((max(other.evidence_turns), participant_id, topic, other))
    if not candidates:
        return None
    _, other_id, topic, other = max(candidates)
    evidence = sorted(set(statement.evidence_turns + other.evidence_turns))
    return Disagreement(
        text=f"围绕{topic}的事实断言出现相反判断",
        evidence_turns=evidence,
        disagreement_type=DisagreementType.FACT_CONFLICT,
        participant_ids=[other_id, speaker_id],
    )

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
    fact_conflict = _fact_conflict(state, turn.participant_id, statement)
    if fact_conflict is not None:
        topic_prefix = fact_conflict.text.split("的事实断言", 1)[0]
        state.disagreements = [
            item for item in state.disagreements
            if item.disagreement_type is not DisagreementType.FACT_CONFLICT
            or not item.text.startswith(topic_prefix)
        ] + [fact_conflict]
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
        target = _procurement_expert(state)
        if target:
            target.good_pass_opportunity = True
            state.intervention = InterventionState(reasons_to_speak=[disagreement], recommended_action=Action.PASS,
                confidence=.85, last_action=previous.intervention.last_action,
                last_agent_turn_id=previous.intervention.last_agent_turn_id,
                human_turns_since_last_intervention=previous.intervention.human_turns_since_last_intervention + 1)
    elif target := _procurement_expert(state):
        topic = next((item for _, item in reversed(positions)
                      if _layer(item.text) == "buying" and any(word in item.text for word in CONTRIBUTION)), None)
        if topic:
            target.good_pass_opportunity = True
            reason = EvidenceStatement(text="采购亲历话题中有尚未发言的相关角色", evidence_turns=topic.evidence_turns)
            state.intervention = InterventionState(reasons_to_speak=[reason], recommended_action=Action.PASS,
                confidence=.82, last_action=previous.intervention.last_action,
                last_agent_turn_id=previous.intervention.last_agent_turn_id,
                human_turns_since_last_intervention=previous.intervention.human_turns_since_last_intervention + 1)
    # Persist the same marginal-value signal that Gate/Router will use. Keeping
    # it on the immutable snapshot prevents clients from seeing stale readiness
    # after a human turn.
    return refresh_close_readiness(TableState.model_validate(state.model_dump()))
