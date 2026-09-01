"""Deterministic active-demand routing for the second product entry point."""

from collections.abc import Sequence
import re

from app.domain import ActiveIntentPreview, ActiveIntentTableCandidate, TableState

MAX_INTENT_CANDIDATES = 5
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
    return text[:120]


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
            reason=(
                "与你提到的公开问题词项相近："
                + "、".join(sorted(overlap)[:3])
            ),
        )
        for _, _, table, overlap in ranked[:limit]
    ]
    return ActiveIntentPreview(
        normalized_question=normalized,
        route="join_existing" if candidates else "new_table",
        candidates=candidates,
    )


__all__ = (
    "MAX_INTENT_CANDIDATES",
    "build_active_intent_preview",
)
