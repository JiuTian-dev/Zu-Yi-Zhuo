"""Deterministic policy for upgrading an async table to a sync session."""

from app.domain import ConversationMode, Level, SafetyLevel, SyncUpgradeDecision, SyncUpgradeSignals, TableState


def evaluate_sync_upgrade(
    state: TableState, signals: SyncUpgradeSignals
) -> SyncUpgradeDecision:
    """Return an explainable upgrade decision without mutating table state."""
    active_member_count = sum(
        person.engagement is Level.HIGH for person in state.participants.values()
    )
    bonuses = [
        label
        for enabled, label in (
            (signals.discussion_quality, "当前讨论质量较高"),
            (signals.external_attention, "外围关注正在增加"),
            (signals.public_value, "问题具有公共价值"),
        )
        if enabled
    ][:3]
    if state.conversation.mode is ConversationMode.SYNC:
        return SyncUpgradeDecision(
            eligible=True,
            core_members_want_continue=True,
            sync_has_extra_value=True,
            active_member_count=active_member_count,
            bonus_signals=bonuses,
            reason="同步讨论已经开始",
        )
    if state.conversation.closed:
        return SyncUpgradeDecision(
            eligible=False,
            core_members_want_continue=False,
            sync_has_extra_value=False,
            active_member_count=active_member_count,
            bonus_signals=bonuses,
            reason="已收桌，不能升级同步",
        )
    if state.conversation.safety_level is SafetyLevel.CRITICAL:
        return SyncUpgradeDecision(
            eligible=False,
            core_members_want_continue=False,
            sync_has_extra_value=False,
            active_member_count=active_member_count,
            bonus_signals=bonuses,
            reason="桌面处于安全暂停，不能升级同步",
        )
    core_members_want_continue = signals.wants_continue and active_member_count >= 2
    sync_has_extra_value = signals.sync_extra_value
    if not core_members_want_continue:
        reason = "至少两位成员需要有持续参与证据，并确认还想继续聊"
    elif not sync_has_extra_value:
        reason = "还没有确认同步相比异步会产生额外价值"
    else:
        reason = "人还想聊，而且值得现在聊"
    return SyncUpgradeDecision(
        eligible=core_members_want_continue and sync_has_extra_value,
        core_members_want_continue=core_members_want_continue,
        sync_has_extra_value=sync_has_extra_value,
        active_member_count=active_member_count,
        bonus_signals=bonuses,
        reason=reason,
    )
