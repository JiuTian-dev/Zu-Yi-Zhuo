"""Explainable table discovery derived from resettable self-scoped behavior."""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import re

from app.domain import (
    BehaviorEvent,
    ParticipantTableRecommendations,
    PersonalizedTableRecommendation,
    TableState,
)
from app.lobby import build_lobby_preview, role_covers_gap
from app.matching import infer_role_gaps

MAX_PERSONALIZATION_EVENTS = 100
MAX_PERSONALIZED_TABLES = 10
_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-z0-9]{2,}")
_SIGNAL_LIMITS = {
    "table_selected": 1,
    "human_message": 3,
    "follow_up_outcome": 2,
}
_SIGNAL_WEIGHTS = {
    "table_selected": 1,
    "human_message": 1,
    "follow_up_outcome": 2,
}
_SIGNAL_TYPE_ORDER = tuple(_SIGNAL_LIMITS)


def _terms(text: str) -> set[str]:
    result = {word.lower() for word in _WORD.findall(text.lower())}
    for chunk in _CJK.findall(text):
        result.update(chunk[index:index + 2] for index in range(len(chunk) - 1))
    return result


def _event_is_usable(event: BehaviorEvent) -> bool:
    if event.event_type not in _SIGNAL_LIMITS:
        return False
    if event.event_type != "follow_up_outcome":
        return True
    return event.detail in {"status:completed", "status:in_progress"}


def _bounded_signals(
    participant_id: str,
    events: Sequence[BehaviorEvent],
    history: Mapping[str, TableState],
) -> list[BehaviorEvent]:
    per_table_type: dict[tuple[str, str], int] = defaultdict(int)
    selected: list[BehaviorEvent] = []
    for event in reversed(events[-MAX_PERSONALIZATION_EVENTS:]):
        if (
            event.participant_id != participant_id
            or event.table_id not in history
            or not _event_is_usable(event)
        ):
            continue
        key = (event.table_id, event.event_type)
        if per_table_type[key] >= _SIGNAL_LIMITS[event.event_type]:
            continue
        per_table_type[key] += 1
        selected.append(event)
    selected.reverse()
    return selected


def _historical_role_weights(
    participant_id: str,
    history: Mapping[str, TableState],
    table_weights: Mapping[str, int],
) -> Counter[str]:
    result: Counter[str] = Counter()
    for table_id, weight in table_weights.items():
        participant = history[table_id].participants.get(participant_id)
        if participant is not None:
            result[participant.role] += weight
    return result


def build_personalized_table_recommendations(
    participant_id: str,
    tables: Sequence[TableState],
    history: Mapping[str, TableState],
    events: Sequence[BehaviorEvent],
    *,
    limit: int = 5,
) -> ParticipantTableRecommendations:
    """Rank eligible public tables without storing a second user profile."""
    if not participant_id.strip():
        raise ValueError("participant_id must be non-empty")
    if limit < 1 or limit > MAX_PERSONALIZED_TABLES:
        raise ValueError(
            f"personalized table limit must be between 1 and {MAX_PERSONALIZED_TABLES}"
        )
    signals = _bounded_signals(participant_id, events, history)
    table_weights: Counter[str] = Counter()
    for event in signals:
        table_weights[event.table_id] += _SIGNAL_WEIGHTS[event.event_type]
    term_weights: Counter[str] = Counter()
    for table_id, weight in table_weights.items():
        historical = history[table_id]
        text = " ".join(filter(None, (historical.core_question, historical.current_subquestion)))
        for term in _terms(text):
            term_weights[term] += weight
    role_weights = _historical_role_weights(participant_id, history, table_weights)
    known_roles = sorted(role_weights, key=lambda role: (-role_weights[role], role))

    ranked: list[tuple[tuple[int, int, int, int, str], PersonalizedTableRecommendation]] = []
    for table in tables:
        if (
            table.conversation.closed
            or table.conversation.soft_expired
            or participant_id in table.participants
            or len(table.participants) >= 5
        ):
            continue
        table_text = " ".join(filter(None, (table.core_question, table.current_subquestion)))
        table_terms = _terms(table_text)
        topic_score = sum(term_weights[term] for term in table_terms)
        history_match: tuple[int, str, TableState] | None = None
        for historical_id, weight in table_weights.items():
            historical = history[historical_id]
            historical_text = " ".join(filter(None, (
                historical.core_question,
                historical.current_subquestion,
            )))
            overlap_score = len(_terms(historical_text) & table_terms) * weight
            candidate = (overlap_score, historical_id, historical)
            if overlap_score and (
                history_match is None
                or overlap_score > history_match[0]
                or (overlap_score == history_match[0] and historical_id < history_match[1])
            ):
                history_match = candidate
        role_gaps = infer_role_gaps(
            participant.role for participant in table.participants.values()
        )
        matched_role: tuple[str, str] | None = next(
            (
                (role, gap)
                for role in known_roles
                for gap in role_gaps
                if role_covers_gap(role, gap)
            ),
            None,
        )
        role_score = role_weights[matched_role[0]] if matched_role else 0
        participant_count = len(table.participants)
        diversity = 3 - len(role_gaps)

        if history_match is not None and matched_role is not None:
            reason = (
                f"这桌延续了你曾关注的“{history_match[2].core_question[:80]}”，"
                f"并缺少{matched_role[1]}视角。"
            )
        elif history_match is not None:
            reason = f"这桌延续了你曾关注的“{history_match[2].core_question[:100]}”。"
        elif matched_role is not None:
            reason = f"基于你过往使用的{matched_role[0][:40]}角色，这桌正缺少{matched_role[1]}视角。"
        elif signals:
            reason = "这是一个与既有参与不同的问题，仍有空席可供探索。"
        else:
            reason = "尚无足够的本人行为信号，先按成桌程度和角色多样性展示公开桌。"
        recommendation = PersonalizedTableRecommendation(
            table_id=table.table_id,
            reason=reason,
            based_on_table_id=history_match[1] if history_match else None,
            based_on_question=history_match[2].core_question[:120] if history_match else None,
            matched_role_gap=matched_role[1] if matched_role else None,
            lobby=build_lobby_preview(table),
        )
        rank = (topic_score, role_score, participant_count, diversity, table.table_id)
        ranked.append((rank, recommendation))

    ranked.sort(key=lambda item: (-item[0][0], -item[0][1], -item[0][2], -item[0][3], item[0][4]))
    signal_types = [
        event_type
        for event_type in _SIGNAL_TYPE_ORDER
        if any(event.event_type == event_type for event in signals)
    ]
    return ParticipantTableRecommendations(
        participant_id=participant_id,
        personalized=bool(signals),
        signal_count=len(signals),
        signal_types=signal_types,
        items=[item[1] for item in ranked[:limit]],
    )


__all__ = (
    "MAX_PERSONALIZATION_EVENTS",
    "MAX_PERSONALIZED_TABLES",
    "build_personalized_table_recommendations",
)
