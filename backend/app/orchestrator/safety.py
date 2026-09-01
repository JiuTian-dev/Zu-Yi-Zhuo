"""Small deterministic safety boundary that runs before the conversation loop."""

from app.domain import SafetyDecision, SafetyLevel, TableState
from app.domain.schemas import EvidenceStatement


# These are deliberately narrow phrase lists.  General discussion of risk,
# moderation, or a news event remains available to the normal conversation.
_PAUSE_KEYWORDS = ("杀人", "杀了", "打死", "砍死", "捅死", "炸死", "威胁", "暴力")
_INTERCEPT_KEYWORDS = ("诈骗", "骗钱", "刷单", "杀猪盘", "骚扰", "人肉", "辱骂")
_BOUNDARY_KEYWORDS = ("闭嘴", "滚开", "别烦我", "废物", "你真蠢")
_ATMOSPHERE_KEYWORDS = ("别吵了", "先冷静", "话说得太冲", "有点火大")


def evaluate_safety(text: str, turn_id: int) -> SafetyDecision:
    """Classify narrow safety tiers without an LLM or hidden policy."""
    for keyword in _PAUSE_KEYWORDS:
        if keyword in text:
            return SafetyDecision(
                blocked=True, action="pause", level=SafetyLevel.CRITICAL,
                reason=f"检测到明确的暴力或威胁关键词：{keyword}", evidence_turns=[turn_id],
            )
    for keyword in _INTERCEPT_KEYWORDS:
        if keyword in text:
            return SafetyDecision(
                blocked=True, action="intercept", level=SafetyLevel.CRITICAL,
                reason=f"检测到明确的骚扰或诈骗关键词：{keyword}", evidence_turns=[turn_id],
            )
    for keyword in _BOUNDARY_KEYWORDS:
        if keyword in text:
            return SafetyDecision(
                blocked=True, action="intercept", level=SafetyLevel.ELEVATED,
                reason="检测到针对成员的人身边界风险，首次触发需要私下提醒",
                evidence_turns=[turn_id],
            )
    for keyword in _ATMOSPHERE_KEYWORDS:
        if keyword in text:
            return SafetyDecision(
                blocked=False, action="allow", level=SafetyLevel.ELEVATED,
                reason="检测到讨论气氛升温，建议把观点与个人分开",
                evidence_turns=[turn_id],
            )
    return SafetyDecision(
        blocked=False, action="allow", level=SafetyLevel.NORMAL,
        reason="未命中明确的高风险关键词",
    )


def escalate_boundary_safety(decision: SafetyDecision, turn_id: int) -> SafetyDecision:
    """Promote a repeated member-boundary violation to a critical pause."""
    if not decision.blocked or decision.level is not SafetyLevel.ELEVATED:
        raise ValueError("only an elevated blocked decision can be escalated")
    return SafetyDecision(
        blocked=True,
        action="pause",
        level=SafetyLevel.CRITICAL,
        reason="同一成员重复触发人身边界风险，已暂停桌面发言并等待审核",
        evidence_turns=[turn_id],
    )


def enforce_safety(previous: TableState, decision: SafetyDecision) -> TableState:
    """Return an immutable safety snapshot without committing the intercepted message."""
    state = previous.model_copy(deep=True)
    state.version += 1
    if decision.blocked:
        state.conversation.safety_level = SafetyLevel.CRITICAL
        state.conversation.state = "safety_paused"
        state.agent.status = "paused"
        state.conversation.risk_flags.append(EvidenceStatement(
            text=decision.reason, evidence_turns=decision.evidence_turns,
        ))
    return TableState.model_validate(state.model_dump())
