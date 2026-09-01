"""Public, deterministic pre-entry table summaries."""

from collections.abc import Sequence

from app.domain import InvitationPreference, LobbyFitPreview, LobbyMemberView, LobbyPreview, ParticipantSeed, TableState
from app.matching import infer_role_gaps

MAX_LOBBY_DISCOVERY = 20


def build_lobby_preview(state: TableState) -> LobbyPreview:
    """Project one table into the bounded contract used by the pre-entry Lobby."""
    participant_count = len(state.participants)
    available_seats = 5 - participant_count
    role_gaps = infer_role_gaps(
        participant.role for participant in state.participants.values()
    )
    if state.conversation.closed:
        table_status = "closed"
    elif state.conversation.soft_expired:
        table_status = "soft_expired"
    else:
        table_status = "open"

    if role_gaps:
        missing_perspective = "这一桌还缺：" + "、".join(role_gaps[:3]) + "视角。"
    elif available_seats > 0:
        missing_perspective = "席位仍开放，欢迎带来不同于现有成员的真实经历。"
    else:
        missing_perspective = "这桌已坐满，暂不再补入新的视角。"

    return LobbyPreview(
        table_id=state.table_id,
        core_question=state.core_question,
        current_subquestion=state.current_subquestion,
        phase=state.phase,
        mode=state.conversation.mode,
        sync_expires_at=state.conversation.sync_expires_at,
        status=table_status,
        state_version=state.version,
        participant_count=participant_count,
        available_seats=available_seats,
        members=[
            LobbyMemberView(
                participant_id=participant.participant_id,
                display_name=participant.display_name,
                role=participant.role,
            )
            for participant in state.participants.values()
        ],
        role_gaps=role_gaps,
        missing_perspective=missing_perspective,
        origin_signal_ids=list(state.origin_signal_ids),
    )


def build_lobby_discovery(
    states: Sequence[TableState],
    *,
    limit: int = MAX_LOBBY_DISCOVERY,
) -> list[LobbyPreview]:
    """Build a stable, bounded directory of public open-table cards."""
    if limit < 1 or limit > MAX_LOBBY_DISCOVERY:
        raise ValueError(f"lobby discovery limit must be between 1 and {MAX_LOBBY_DISCOVERY}")
    open_states = sorted(
        (
            state
            for state in states
            if not state.conversation.closed and not state.conversation.soft_expired
        ),
        key=lambda state: state.table_id,
    )
    return [build_lobby_preview(state) for state in open_states[:limit]]


_ROLE_GAP_TERMS = {
    "实践者": ("实践", "落地", "运营", "业务", "创业", "practitioner"),
    "专业者": ("研究", "技术", "架构", "专家", "安全", "research", "engineer"),
    "处境者": ("产品", "用户", "处境", "一线", "提问", "product", "user"),
}


def _role_covers_gap(role: str, gap: str) -> bool:
    role_text = role.lower()
    return any(term in role_text for term in _ROLE_GAP_TERMS.get(gap, ()))


def build_lobby_fit_preview(
    state: TableState,
    candidate: ParticipantSeed,
    *,
    blocked: bool = False,
) -> LobbyFitPreview:
    """Explain a possible seat using only the candidate's role and table gaps."""
    if state.conversation.closed:
        return LobbyFitPreview(
            table_id=state.table_id,
            participant_id=candidate.participant_id,
            eligible=False,
            reason="这桌已经结束，暂不接受新的入席。",
        )
    if state.conversation.soft_expired:
        return LobbyFitPreview(
            table_id=state.table_id,
            participant_id=candidate.participant_id,
            eligible=False,
            reason="这桌已暂时停下，暂不接受新的入席。",
        )
    if candidate.participant_id in state.participants:
        return LobbyFitPreview(
            table_id=state.table_id,
            participant_id=candidate.participant_id,
            eligible=False,
            reason="你已经在这桌里。",
        )
    if candidate.roundtable_invite_preference is InvitationPreference.NONE:
        return LobbyFitPreview(
            table_id=state.table_id,
            participant_id=candidate.participant_id,
            eligible=False,
            reason="你当前选择了不接收圆桌邀请。",
        )
    if len(state.participants) >= 5:
        return LobbyFitPreview(
            table_id=state.table_id,
            participant_id=candidate.participant_id,
            eligible=False,
            reason="这桌已坐满，暂时没有可用席位。",
        )
    if blocked:
        return LobbyFitPreview(
            table_id=state.table_id,
            participant_id=candidate.participant_id,
            eligible=False,
            reason="当前匹配偏好不适合这张桌。",
        )

    role_gaps = infer_role_gaps(
        participant.role for participant in state.participants.values()
    )
    role_label = candidate.role.strip()[:80]
    matched_gap = next(
        (gap for gap in role_gaps if _role_covers_gap(role_label, gap)),
        None,
    )
    if matched_gap is not None:
        reason = f"这一桌缺少{matched_gap}视角，你的{role_label}可以补上这块经验。"
    elif role_gaps:
        reason = f"这一桌还缺{role_gaps[0]}视角，你的{role_label}能带来不同切面。"
    else:
        reason = f"这一桌已有多种角色，你的{role_label}能增加一个新的经验切面。"
    return LobbyFitPreview(
        table_id=state.table_id,
        participant_id=candidate.participant_id,
        eligible=True,
        matched_role_gap=matched_gap,
        reason=reason,
    )


__all__ = (
    "MAX_LOBBY_DISCOVERY",
    "build_lobby_discovery",
    "build_lobby_fit_preview",
    "build_lobby_preview",
)
