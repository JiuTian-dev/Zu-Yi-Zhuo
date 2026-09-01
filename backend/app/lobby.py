"""Public, deterministic pre-entry table summaries."""

from app.domain import LobbyMemberView, LobbyPreview, TableState
from app.matching import infer_role_gaps


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


__all__ = ("build_lobby_preview",)
