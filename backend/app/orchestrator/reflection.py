"""Deterministic, evidence-backed post-intervention effect evaluation."""
from collections.abc import Sequence
from app.domain import Action, ReflectionResult, RouteDecision, TableState
from app.domain.schemas import EvidenceStatement
def _ids(*values) -> list[int]:
    result: set[int] = set()
    for value in values:
        if isinstance(value, int):
            result.add(value)
        elif getattr(value, "evidence_turns", None) is not None:
            result.update(value.evidence_turns)
        elif value is not None:
            for item in value:
                result.update(getattr(item, "evidence_turns", ()) or ())
    return sorted(result)
def _state_ids(state: TableState) -> list[int]:
    values = [state.new_insights, state.consensus, state.disagreements, state.open_loops,
              state.conversation.most_promising_thread, state.conversation.risk_flags]
    values += [x for p in state.participants.values() for x in (p.current_position, p.key_contributions)]
    return _ids(*values)
def _statement(text: str, evidence: list[int]) -> EvidenceStatement | None:
    return EvidenceStatement(text=text, evidence_turns=evidence) if evidence else None
def _post_ids(before: TableState, after: TableState, human_turn_ids: Sequence[int] | None) -> list[int]:
    before_ids, after_ids = set(_state_ids(before)), set(_state_ids(after))
    if human_turn_ids is not None:
        return sorted({i for i in human_turn_ids if isinstance(i, int) and not isinstance(i, bool) and i > 0} & (after_ids - before_ids))
    return sorted(i for i in after_ids - before_ids if i > 0)
def _post_evidence(values, post_ids: set[int]) -> list[int]:
    return sorted(set(_ids(*values)).intersection(post_ids))
def evaluate_reflection(
    before: TableState, after: TableState, intervention: RouteDecision,
    human_turn_ids: Sequence[int] | None = None,
) -> ReflectionResult:
    """Evaluate only after the cooldown has supplied at least two human turns."""
    if before.table_id != after.table_id:
        raise ValueError("before and after must belong to the same table")
    turns = after.intervention.human_turns_since_last_intervention
    if turns < 2:
        return ReflectionResult(intervention_id=after.intervention.last_agent_turn_id or f"{after.table_id}:v{before.version}",
            table_id=after.table_id, state_version=after.version, intervention_action=intervention.action,
            human_turns_observed=turns, effective=False, score=0, confidence=0,
            strategy_note="真人回应不足 2 个 turn，暂不判断介入是否有效。")
    post_ids = set(_post_ids(before, after, human_turn_ids))
    if not post_ids:
        return ReflectionResult(intervention_id=after.intervention.last_agent_turn_id or f"{after.table_id}:v{before.version}",
            table_id=after.table_id, state_version=after.version, intervention_action=intervention.action,
            human_turns_observed=turns, effective=False, score=0, confidence=0.4,
            strategy_note="已有真人回应，但缺少可归因的 post-intervention turn evidence。")
    effects: list[EvidenceStatement] = []
    target = intervention.target_participant_id
    person = after.participants.get(target) if target else None
    before_person = before.participants.get(target) if target else None
    target_joined = person is not None and (before_person is None or
                    (before_person.last_spoke_turn is None and person.last_spoke_turn is not None))
    if target_joined:
        evidence = _post_evidence((person.current_position, person.key_contributions), post_ids)
        if item := _statement(f"目标参与者 {person.display_name} 加入了讨论。", evidence): effects.append(item)
    if before.current_subquestion != after.current_subquestion and after.current_subquestion:
        evidence = _post_evidence((after.open_loops, after.new_insights, after.conversation.most_promising_thread), post_ids)
        if item := _statement(f"讨论形成了新的追问：{after.current_subquestion}", evidence): effects.append(item)
    old_insights = {(x.text, tuple(x.evidence_turns)) for x in before.new_insights}
    for insight in after.new_insights:
        if (insight.text, tuple(insight.evidence_turns)) not in old_insights:
            if item := _statement(insight.text, _post_evidence((insight,), post_ids)): effects.append(item)
    old_consensus = {(x.text, tuple(x.evidence_turns)) for x in before.consensus}
    for item in after.consensus:
        if (item.text, tuple(item.evidence_turns)) not in old_consensus:
            if statement := _statement(item.text, _post_evidence((item,), post_ids)): effects.append(statement)
    if len(after.disagreements) < len(before.disagreements):
        evidence = _post_evidence((before.disagreements,), post_ids)
        if item := _statement("有一处分歧被收束了。", evidence): effects.append(item)
    evidence = sorted(post_ids)
    negative: list[EvidenceStatement] = []
    if not effects:
        if item := _statement("介入后暂未观察到可归因的新推进。", evidence): negative.append(item)
    elif after.disagreements:
        if item := _statement("仍有分歧未解决，下一轮需要继续核对。", _post_evidence((after.disagreements,), post_ids)): negative.append(item)
    score = min(1.0, max(0.0, 0.45 + 0.25 * len(effects) - 0.10 * len(negative)))
    effective = bool(effects) and score >= 0.5
    note = "介入带来了可观察推进，可沿新问题继续。" if effective else "推进有限，下一次介入应缩小问题并补足证据。"
    return ReflectionResult(intervention_id=after.intervention.last_agent_turn_id or f"{after.table_id}:v{before.version}",
        table_id=after.table_id, state_version=after.version, intervention_action=intervention.action,
        human_turns_observed=turns, effective=effective, score=score,
        confidence=min(1.0, 0.55 + 0.1 * min(turns, 3)), effects=effects,
        negative_effects=negative, strategy_note=note)
__all__ = ("evaluate_reflection",)
