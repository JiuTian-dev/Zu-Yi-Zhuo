"""Close-readiness and evidence-backed close artifacts."""
from collections.abc import Sequence
import re
from app.domain import (
    FollowUpItem, HumanTurn, Level, PersonalCard, SharedBaseline, StageSummary, TableState,
)
from app.domain.schemas import EvidenceStatement, RelationshipSuggestion
def _evidence(*items) -> list[int]:
    ids: set[int] = set()
    for item in items:
        if item is None:
            continue
        if isinstance(item, int):
            ids.add(item)
        elif isinstance(item, (list, tuple, set)):
            ids.update(_evidence(*item))
        else:
            ids.update(getattr(item, "evidence_turns", ()) or ())
    return sorted(ids)
def _state_evidence(state: TableState) -> list[int]:
    items = [state.new_insights, state.consensus, state.disagreements, state.open_loops,
             state.conversation.most_promising_thread, state.conversation.risk_flags]
    return _evidence(items, [[p.current_position, p.key_contributions] for p in state.participants.values()])
def compute_close_readiness(state: TableState) -> Level:
    """Estimate whether another turn's marginal value has begun to decline."""
    unresolved = len(state.open_loops) + len(state.disagreements)
    substance = len(state.new_insights) + len(state.consensus)
    if state.phase.value == "close" and substance and unresolved == 0:
        return Level.HIGH
    if state.momentum is Level.LOW and substance and unresolved == 0:
        return Level.HIGH
    if state.momentum is Level.LOW and substance:
        return Level.MEDIUM
    return Level.MEDIUM if state.momentum is Level.MEDIUM and substance >= 2 and unresolved <= 1 else Level.LOW
def refresh_close_readiness(state: TableState) -> TableState:
    """Return a fresh snapshot with readiness derived from current table signals."""
    refreshed = state.model_copy(deep=True)
    refreshed.close_readiness = compute_close_readiness(state)
    return TableState.model_validate(refreshed.model_dump())
def _suggestion(text: str, evidence_turns: list[int]) -> FollowUpItem | None:
    if not evidence_turns:
        return None
    return FollowUpItem(item_type="suggestion", text=text, is_commitment=False, evidence_turns=evidence_turns)
def build_shared_baseline(state: TableState, core_question_before: str | None = None,
                          turns: Sequence[HumanTurn] | None = None,
                          latest_summary: StageSummary | None = None) -> SharedBaseline:
    """Build the shared close card without converting open loops into commitments."""
    summary = latest_summary if latest_summary is not None and (
        latest_summary.table_id == state.table_id
        and latest_summary.summary_id == state.latest_stage_summary_id
        and latest_summary.revision == state.latest_stage_summary_revision
    ) else None
    summary_items = [
        *(summary.clarified if summary else []),
        *(summary.disagreements if summary else []),
        *(summary.missing if summary else []),
        *([summary.next_focus] if summary and summary.next_focus else []),
    ]
    evidence = _evidence(summary_items, state.open_loops, state.conversation.most_promising_thread)
    if not evidence:
        evidence = _state_evidence(state)
    if not evidence:
        raise ValueError("cannot build a baseline without turn evidence")
    question = summary.next_focus.text if summary and summary.next_focus else (state.current_subquestion or state.core_question)
    next_steps = [item for loop in state.open_loops if (item := _suggestion(loop.question, list(loop.evidence_turns)))]
    # Synthetic demo speech can contain words such as “可以” without being a
    # commitment by the real participant. Only human speech becomes a take-away.
    next_steps += extract_follow_ups([turn for turn in turns if turn.source == "human"]) if turns else []
    evolved = EvidenceStatement(text=question, evidence_turns=evidence)
    return SharedBaseline(table_id=state.table_id, state_version=state.version,
        core_question_before=core_question_before or state.core_question,
        key_consensus=list(summary.clarified if summary else state.consensus),
        unresolved_disagreements=list(summary.disagreements if summary else state.disagreements),
        evolved_question=evolved, collective_next_steps=next_steps)
def build_personal_card(state: TableState, participant_id: str,
                        latest_summary: StageSummary | None = None) -> PersonalCard:
    """Build one participant's view; unknown IDs are rejected rather than guessed."""
    person = state.participants.get(participant_id)
    if person is None:
        raise ValueError(f"unknown participant: {participant_id}")
    summary = latest_summary if latest_summary is not None and (
        latest_summary.table_id == state.table_id
        and latest_summary.summary_id == state.latest_stage_summary_id
        and latest_summary.revision == state.latest_stage_summary_revision
    ) else None
    changed = list(summary.clarified if summary else state.new_insights)
    contribution = list(person.key_contributions)
    if not contribution and person.current_position:
        contribution = [person.current_position]
    relationships: list[RelationshipSuggestion] = []
    for disagreement in state.disagreements:
        if participant_id not in disagreement.participant_ids:
            continue
        for other_id in disagreement.participant_ids:
            if other_id != participant_id and other_id in state.participants:
                relationships.append(RelationshipSuggestion(
                    participant_id=other_id, reason="可继续交叉验证这处分歧",
                    evidence_turns=list(disagreement.evidence_turns)))
    if not relationships:
        for other_id, other in state.participants.items():
            if other_id != participant_id and other.current_position:
                relationships.append(RelationshipSuggestion(
                    participant_id=other_id, reason="可继续交换这一侧的现场经验",
                    evidence_turns=list(other.current_position.evidence_turns)))
                if len(relationships) == 3:
                    break
    actions = [item for loop in state.open_loops if (item := _suggestion(loop.question, list(loop.evidence_turns)))]
    return PersonalCard(table_id=state.table_id, participant_id=participant_id, state_version=state.version,
        what_changed=changed, your_contribution=contribution, worth_continuing_with=relationships,
        suggested_next_actions=actions[:3])
_COMMITMENT = re.compile(r"我会|我们约|我来做|我负责")
_SUGGESTION = re.compile(r"(?:可以|建议|不妨|下一步|需要|先)[^。！？]{1,100}")
def extract_follow_ups(turns: Sequence[HumanTurn]) -> list[FollowUpItem]:
    """Extract explicit commitments and tentative suggestions from human text."""
    result: list[FollowUpItem] = []
    for raw_turn in turns:
        turn = raw_turn if isinstance(raw_turn, HumanTurn) else HumanTurn.model_validate(raw_turn)
        text = turn.text.strip()
        if _COMMITMENT.search(text):
            result.append(FollowUpItem(item_type="commitment", text=text, is_commitment=True,
                owner_participant_id=turn.participant_id, evidence_turns=[turn.turn_id]))
        elif _SUGGESTION.search(text):
            result.append(FollowUpItem(item_type="suggestion", text=text, is_commitment=False, evidence_turns=[turn.turn_id]))
    return result
__all__ = ("build_personal_card", "build_shared_baseline", "compute_close_readiness", "extract_follow_ups", "refresh_close_readiness")
