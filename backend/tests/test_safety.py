from app.domain import SafetyLevel
from app.orchestrator import build_initial_state, enforce_safety, evaluate_safety


def test_safe_text_is_allowed() -> None:
    decision = evaluate_safety("我们讨论一下采购的实际风险。", 1)
    assert not decision.blocked and decision.action == "allow"


def test_hard_keyword_is_blocked_with_hard_enforcement() -> None:
    decision = evaluate_safety("我会威胁你。", 3)
    assert decision.blocked and decision.action in {"pause", "intercept", "remove"}
    assert decision.evidence_turns == [3]


def test_enforcement_is_copy_on_write_and_records_critical_evidence() -> None:
    previous = build_initial_state("safety", "如何推进讨论？", [])
    decision = evaluate_safety("这是一场诈骗。", 1)
    state = enforce_safety(previous, decision)
    assert previous.version == 0 and previous.conversation.risk_flags == []
    assert state.version == 1 and state.conversation.safety_level is SafetyLevel.CRITICAL
    assert state.conversation.state == "safety_paused"
    assert state.conversation.risk_flags[0].evidence_turns == [1]
