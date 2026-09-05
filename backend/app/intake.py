"""Deterministic active-demand routing for the second product entry point."""

from collections.abc import Sequence
import re

from app.domain import ActiveIntentPreview, ActiveIntentTableCandidate, TableState
from app.lobby import build_lobby_preview

MAX_INTENT_CANDIDATES = 5
MAX_INTENT_QUESTION_LENGTH = 120
_GENERIC_INTENTS = {
    "找人聊",
    "找人聊天",
    "找人交流",
    "一起聊聊",
    "认识同行",
    "找人一起做",
}
_STOP_TERMS = {
    "想找",
    "找人",
    "聊聊",
    "聊天",
    "交流",
    "一起",
    "可以",
    "一下",
    "关于",
    "这个",
    "那个",
    "请问",
    "我想",
    "希望",
    "最近",
    # Common relationship/experience wording is not enough to establish that
    # two questions are about the same table. Keeping these out of the CJK
    # bigram set prevents "做过…的人" from matching unrelated topics.
    "做过",
    "的人",
    "真正",
}
_PREFIXES = (
    "我想找人聊聊",
    "我想找人聊",
    "我想和人聊聊",
    "我想和人聊",
    "我正在思考",
    "我最近在想",
    "我希望围绕",
    "我希望聊聊",
    "想找人一起",
    "想和人一起",
)


def _normalise_message(message: str) -> str:
    text = " ".join(message.split()).strip(" ：:，,。！？?!")
    original = text
    for prefix in _PREFIXES:
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix):].strip(" ：:，,。！？?!")
            break
    if not text:
        text = original
    return text[:MAX_INTENT_QUESTION_LENGTH]


def _terms(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text).lower()
    terms = {
        token
        for token in re.findall(r"[a-z0-9]{2,}", compact)
        if token not in _STOP_TERMS
    }
    cjk = re.findall(r"[\u4e00-\u9fff]", compact)
    terms.update(
        "".join(cjk[index:index + 2])
        for index in range(len(cjk) - 1)
    )
    return {term for term in terms if term not in _STOP_TERMS}


def _is_generic_intent(normalized: str) -> bool:
    compact = re.sub(r"\s+", "", normalized)
    return len(compact) < 8 or compact in _GENERIC_INTENTS


def build_active_intent_preview(
    message: str,
    tables: Sequence[TableState],
    *,
    limit: int = MAX_INTENT_CANDIDATES,
) -> ActiveIntentPreview:
    """Route one active request without persisting it or reading private context."""
    if limit < 1 or limit > MAX_INTENT_CANDIDATES:
        raise ValueError(f"active intent limit must be between 1 and {MAX_INTENT_CANDIDATES}")
    normalized = _normalise_message(message)
    if _is_generic_intent(normalized):
        return ActiveIntentPreview(
            normalized_question=normalized,
            route="clarify",
            clarifying_question="你想围绕哪个具体问题，邀请有不同经历的人一起聊？",
        )

    intent_terms = _terms(normalized)
    ranked: list[tuple[int, str, TableState, set[str]]] = []
    for table in tables:
        participant_count = len(table.participants)
        if participant_count >= 5:
            continue
        table_text = " ".join(
            value
            for value in (table.core_question, table.current_subquestion)
            if value
        )
        overlap = intent_terms & _terms(table_text)
        if overlap:
            ranked.append((len(overlap), table.table_id, table, overlap))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    candidates = [
        ActiveIntentTableCandidate(
            table_id=table.table_id,
            core_question=table.core_question,
            current_subquestion=table.current_subquestion,
            mode=table.conversation.mode,
            participant_count=len(table.participants),
            available_seats=5 - len(table.participants),
            reason=(
                "与你提到的公开问题词项相近："
                + "、".join(sorted(overlap)[:3])
            ),
            origin_signal_ids=list(table.origin_signal_ids),
            lobby=build_lobby_preview(table),
        )
        for _, _, table, overlap in ranked[:limit]
    ]
    return ActiveIntentPreview(
        normalized_question=normalized,
        route="join_existing" if candidates else "new_table",
        candidates=candidates,
    )


def merge_active_intent_messages(messages: Sequence[str]) -> str:
    """Build one bounded question while preserving the most recent clarification."""
    normalized = [_normalise_message(message) for message in messages if message.strip()]
    if not normalized:
        raise ValueError("active intent messages must not be empty")
    if len(normalized) > 1:
        meaningful = [
            message
            for message in normalized
            if re.sub(r"\s+", "", message) not in _GENERIC_INTENTS
        ]
        normalized = meaningful or [normalized[-1]]

    selected_reversed: list[str] = []
    used = 0
    for message in reversed(normalized):
        separator_length = 1 if selected_reversed else 0
        available = MAX_INTENT_QUESTION_LENGTH - used - separator_length
        if available <= 0:
            break
        selected_reversed.append(message[-available:])
        used += min(len(message), available) + separator_length
    return "；".join(reversed(selected_reversed))


def build_active_intent_session_preview(
    messages: Sequence[str],
    tables: Sequence[TableState],
    *,
    limit: int = MAX_INTENT_CANDIDATES,
) -> ActiveIntentPreview:
    """Route the current bounded conversation context without persisting it."""
    return build_active_intent_preview(
        merge_active_intent_messages(messages),
        tables,
        limit=limit,
    )


__all__ = (
    "MAX_INTENT_CANDIDATES",
    "build_active_intent_preview",
    "build_active_intent_session_preview",
    "merge_active_intent_messages",
)
