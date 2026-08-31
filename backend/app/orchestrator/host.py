"""Deterministic, replaceable Chinese Host wording for routed actions."""

from __future__ import annotations
import re
from app.domain import Action, AgentActionEvent, DisagreementType, GroundingCard, RouteDecision, SafetyLevel, TableState
_BANNED = ("检测到", "根据分析", "作为AI")
def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _safe(value: str, limit: int = 64) -> str:
    """Keep state text readable without leaking system-language into Host speech."""
    result = _compact(value)
    for term in _BANNED:
        result = result.replace(term, "这件事")
    return result[:limit].rstrip("，、：；")
def _fit(value: str, limit: int = 120) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip("，、：； ") + "。"


def _target(state: TableState, participant_id: str | None):
    return state.participants.get(participant_id) if participant_id else None
def _probe_text(state: TableState) -> str:
    question = state.current_subquestion
    if question is None and state.open_loops:
        question = state.open_loops[0].question
    question = _safe(question or state.core_question, 52)
    return _fit(f'围绕“{question}”，能不能补一个具体例子？再说说它的原因和适用边界？')
def _pass_text(state: TableState, participant_id: str | None) -> str:
    person = _target(state, participant_id)
    if person is None:
        raise ValueError("PASS target_participant_id must identify a participant in state")
    experience = (
        person.unused_relevant_experience[0]
        if person.profile_shared and person.unused_relevant_experience
        else None
    )
    if experience:
        text = (f'{person.display_name}，你的角色是{_safe(person.role, 28)}，而且有“{_safe(experience.text, 40)}”这段经历。'
                "能不能从现场讲讲，它为什么改变了你的判断？")
    else:
        text = (f'{person.display_name}，你的角色是{_safe(person.role, 28)}，这件事正好需要这一侧的经验。'
                "能不能讲一个具体现场？")
    return _fit(text)
def _reframe_text(state: TableState, participant_id: str | None, evidence_turns: list[int] | None = None) -> str:
    route_evidence = set(evidence_turns or ())
    disagreement = next((item for item in state.disagreements if route_evidence.intersection(item.evidence_turns)), None)
    disagreement = disagreement or (state.disagreements[0] if state.disagreements else None)
    kind = disagreement.disagreement_type if disagreement else None
    if kind is DisagreementType.LAYER_MISMATCH:
        text = "我们现在把技术实现和采购决策放在同一层比较了。先把两条链拆开：技术回答“能不能做”，采购回答“谁来承担”。"
    elif kind is DisagreementType.DEFINITION_MISMATCH:
        text = "我们对关键概念的指向还没对齐。先把定义说清，再比较不同答案。"
    elif kind is DisagreementType.CAUSAL_DISAGREEMENT:
        text = "我们先把结论和原因链分开：结论可以相近，原因仍要逐段核对。"
    elif kind is DisagreementType.VALUE_CONFLICT:
        text = "这里其实有两套取舍标准。先说清各自优先保护什么，再看能否形成共同判断。"
    else:
        text = "我们先换一个框架，把事实、判断和责任边界分别说清，再接着比较。"
    person = _target(state, participant_id)
    if person:
        text += f"{person.display_name}，你能接着补上自己这一侧吗？"
    return _fit(text)
def _close_text(state: TableState) -> str:
    core = _safe(state.core_question, 40)
    if state.current_subquestion:
        next_question = _safe(state.current_subquestion, 48)
        return _fit(f'我们先收束到这里。原问题“{core}”留下的新追问是“{next_question}”，之后可以继续验证。')
    return _fit(f'今天先收束到这里，回到原问题“{core}”，留一道问题给下一轮继续聊。')
def _ground_text(card: GroundingCard) -> str:
    title = _compact(card.title)
    excerpt = _compact(card.excerpt)
    source = _compact(card.source_ref)
    excerpt_end = "" if excerpt.endswith(("。", "！", "？")) else "。"
    text = f'我先放上「{title}」：{excerpt}{excerpt_end}来源：{source}。大家可以据此核对。'
    if len(text) <= 120:
        return text
    # Preserve the source identity while fitting the event's hard text limit.
    title = title[:28].rstrip("，、：； ")
    source = source[:28].rstrip("，、：； ")
    fixed = len(f'我先放上「{title}」：{excerpt_end}来源：{source}。大家可以据此核对。')
    excerpt = excerpt[: max(8, 120 - fixed)].rstrip("，、：； ")
    excerpt_end = "" if excerpt.endswith(("。", "！", "？")) else "。"
    return _fit(f'我先放上「{title}」：{excerpt}{excerpt_end}来源：{source}。大家可以据此核对。')
def _hint(action: Action, target_participant_id: str | None = None) -> dict:
    focus = [target_participant_id] if target_participant_id else []
    return {
        Action.SILENCE: {"kind": "silence", "focus": focus},
        Action.PASS: {"kind": "pass", "focus": focus, "accent": "invite"},
        Action.PROBE: {"kind": "probe", "focus": ["question"]},
        Action.REFRAME: {"kind": "reframe", "focus": focus, "show_structure": True},
        Action.GROUND: {"kind": "ground", "focus": ["source"]},
        Action.CLOSE: {"kind": "close", "focus": ["summary", "next_question"]},
    }[action]
def generate_host_event(
    state: TableState,
    route: RouteDecision,
    grounding_card: GroundingCard | None = None,
) -> AgentActionEvent:
    """Render one routed action into a frontend-safe AgentActionEvent.

    This is intentionally deterministic. A future LLM Host can replace the
    wording helpers while retaining this event contract and its fallbacks.
    """
    if state.conversation.safety_level is SafetyLevel.CRITICAL:
        return AgentActionEvent(
            action=Action.SILENCE, text=None, visual_hint=_hint(Action.SILENCE),
            evidence_turns=list(route.evidence_turns), state_version=state.version,
            confidence=route.confidence,
        )
    action = route.action
    if route.target_participant_id and route.target_participant_id not in state.participants:
        return AgentActionEvent(action=Action.SILENCE, visual_hint={"kind": "silence", "focus": []},
                                evidence_turns=list(route.evidence_turns), state_version=state.version,
                                confidence=route.confidence)
    card = None
    if grounding_card is not None:
        try:
            card = (grounding_card if isinstance(grounding_card, GroundingCard)
                    else GroundingCard.model_validate(grounding_card))
            if not all(_compact(value) for value in (card.title, card.excerpt, card.source_ref)):
                card = None
        except (TypeError, ValueError):
            card = None

    if action is Action.SILENCE:
        text = None
        visual_hint = _hint(action, route.target_participant_id)
    elif action is Action.PASS:
        text = _pass_text(state, route.target_participant_id)
        visual_hint = _hint(action, route.target_participant_id)
    elif action is Action.PROBE:
        text = _probe_text(state)
        visual_hint = _hint(action)
    elif action is Action.REFRAME:
        text = _reframe_text(state, route.target_participant_id, route.evidence_turns)
        visual_hint = _hint(action, route.target_participant_id)
    elif action is Action.GROUND and card is not None:
        text = _ground_text(card)
        visual_hint = {**_hint(action), "source_ref": card.source_ref}
    elif action is Action.GROUND:
        # A missing/invalid source must never become an invented fact.
        action = Action.PROBE
        text = _probe_text(state)
        visual_hint = {**_hint(action), "fallback_from": Action.GROUND.value}
    elif action is Action.CLOSE:
        text = _close_text(state)
        visual_hint = _hint(action)
    else:  # pragma: no cover - Action is a closed StrEnum, kept for safe defaults.
        action = Action.SILENCE
        text = None
        visual_hint = _hint(action)

    return AgentActionEvent(
        action=action,
        target_participant_id=None if route.action is Action.GROUND and card is None else route.target_participant_id,
        text=text,
        visual_hint=visual_hint,
        evidence_turns=list(route.evidence_turns),
        state_version=state.version,
        confidence=route.confidence,
    )


__all__ = ("generate_host_event", "GroundingCard")
