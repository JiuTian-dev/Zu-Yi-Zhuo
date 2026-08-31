"""Small deterministic safety boundary that runs before the conversation loop."""

from app.domain import SafetyDecision, SafetyLevel, TableState
from app.domain.schemas import EvidenceStatement


# These are deliberately narrow, explicit hard-violation terms.  General discussion
# of risk, moderation, or a news event remains available to the normal conversation.
_PAUSE_KEYWORDS = ("杀人", "杀了", "打死", "砍死", "捅死", "炸死", "威胁", "暴力")
_INTERCEPT_KEYWORDS = ("诈骗", "骗钱", "刷单", "杀猪盘", "骚扰", "人肉", "辱骂")


def evaluate_safety(text: str, turn_id: int) -> SafetyDecision:
    """Classify only explicit hard-violation language; no LLM or hidden policy."""
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
    return SafetyDecision(
        blocked=False, action="allow", level=SafetyLevel.NORMAL,
        reason="未命中明确的高风险关键词",
    )


def enforce_safety(previous: TableState, decision: SafetyDecision) -> TableState:
    """Return an immutable safety snapshot without committing the intercepted message."""
    state = previous.model_copy(deep=True)
    state.version += 1
    if decision.blocked:
        state.conversation.safety_level = SafetyLevel.CRITICAL
        state.conversation.state = "safety_paused"
        state.conversation.risk_flags.append(EvidenceStatement(
            text=decision.reason, evidence_turns=decision.evidence_turns,
        ))
    return TableState.model_validate(state.model_dump())
