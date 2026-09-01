"""Explainable, safety-aware suggestions for peripheral comment promotion."""

from collections.abc import Sequence
import re

from app.domain import (
    CommentPromotion,
    CommentPromotionCandidate,
    CommentPromotionCandidates,
    PeripheralComment,
    TableState,
)
from app.orchestrator import evaluate_safety

MAX_COMMENT_CURATION_INPUTS = 100
MAX_COMMENT_PROMOTION_CANDIDATES = 10
_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-z0-9]{2,}")
_QUESTION_MARKERS = (
    "?", "？", "为什么", "怎么", "如何", "是否", "能否", "什么", "哪种", "哪些",
)
_EXPERIENCE_MARKERS = (
    "案例", "经历", "亲历", "实践", "数据", "证据", "样本", "例子", "具体", "我曾", "我们曾",
)
_STOP_TERMS = {
    "一个", "这个", "我们", "可以", "问题", "讨论", "什么", "怎么", "如何", "是否", "为什", "哪些",
}


def _terms(text: str) -> set[str]:
    result = {word.lower() for word in _WORD.findall(text.lower())}
    for chunk in _CJK.findall(text):
        result.update(chunk[index:index + 2] for index in range(len(chunk) - 1))
    return result - _STOP_TERMS


def _context_text(state: TableState) -> str:
    pieces = [state.core_question, state.current_subquestion or ""]
    pieces.extend(item.text for item in state.new_insights)
    pieces.extend(item.text for item in state.consensus)
    pieces.extend(item.text for item in state.disagreements)
    pieces.extend(item.question for item in state.open_loops)
    return " ".join(pieces)


def build_comment_promotion_candidates(
    state: TableState,
    comments: Sequence[PeripheralComment],
    promotions: Sequence[CommentPromotion],
    *,
    limit: int = 5,
) -> CommentPromotionCandidates:
    """Rank safe, unpromoted comments without mutating moderation or table state."""
    if limit < 1 or limit > MAX_COMMENT_PROMOTION_CANDIDATES:
        raise ValueError(
            f"comment promotion candidate limit must be between 1 and "
            f"{MAX_COMMENT_PROMOTION_CANDIDATES}"
        )
    promoted_ids = {
        item.comment_id
        for item in promotions
        if item.table_id == state.table_id
    }
    context_terms = _terms(_context_text(state))
    ranked: list[tuple[tuple[int, int, int, int, str], CommentPromotionCandidate]] = []
    bounded_comments = [
        comment for comment in comments if comment.table_id == state.table_id
    ][-MAX_COMMENT_CURATION_INPUTS:]
    for index, comment in enumerate(bounded_comments):
        if comment.comment_id in promoted_ids:
            continue
        safety = evaluate_safety(comment.text, max(1, index + 1))
        if safety.blocked:
            continue
        comment_terms = _terms(comment.text)
        matched_topics = sorted(context_terms & comment_terms)[:5]
        is_question = any(marker in comment.text for marker in _QUESTION_MARKERS)
        has_experience = any(marker in comment.text for marker in _EXPERIENCE_MARKERS)
        if not matched_topics and not (is_question and has_experience):
            continue
        signals: list[str] = []
        if matched_topics:
            signals.append("topic_match")
        if is_question:
            signals.append("question")
        if has_experience:
            signals.append("experience")
        topic_label = "、".join(matched_topics[:3])
        if matched_topics and is_question and has_experience:
            reason = f"与当前讨论的“{topic_label}”相关，并提出了带案例或经历线索的问题。"
        elif matched_topics and is_question:
            reason = f"与当前讨论的“{topic_label}”相关，并提出了一个可继续追问的问题。"
        elif matched_topics and has_experience:
            reason = f"与当前讨论的“{topic_label}”相关，并带有可验证的案例或经历线索。"
        elif matched_topics:
            reason = f"补充了当前讨论中“{topic_label}”相关的外围视角。"
        else:
            reason = "提出了一个带案例或经历线索的明确问题，值得由核心成员判断是否递进。"
        candidate = CommentPromotionCandidate(
            comment=comment,
            reason=reason,
            signals=signals,
            matched_topics=matched_topics,
        )
        score = len(matched_topics) * 4 + int(is_question) * 3 + int(has_experience) * 2
        rank = (score, int(is_question), int(has_experience), index, comment.comment_id)
        ranked.append((rank, candidate))
    ranked.sort(
        key=lambda item: (
            -item[0][0], -item[0][1], -item[0][2], -item[0][3], item[0][4]
        )
    )
    return CommentPromotionCandidates(
        table_id=state.table_id,
        state_version=state.version,
        total=len(ranked),
        limit=limit,
        items=[item[1] for item in ranked[:limit]],
    )


__all__ = (
    "MAX_COMMENT_CURATION_INPUTS",
    "MAX_COMMENT_PROMOTION_CANDIDATES",
    "build_comment_promotion_candidates",
)
