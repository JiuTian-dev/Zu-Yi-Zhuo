from app.demo import flagship_participants
from app.domain import ConversationMode, HumanTurn, SyncUpgradeSignals
from app.orchestrator import build_initial_state, evaluate_sync_upgrade, observe_turn


def _active_state():
    state = build_initial_state("mode", "Q", flagship_participants)
    state = observe_turn(state, HumanTurn(turn_id=1, participant_id="architect", text="我亲历过一次试点。"))
    return observe_turn(state, HumanTurn(turn_id=2, participant_id="product", text="我也补充一条现场经验。"))


def test_sync_upgrade_requires_two_hard_conditions() -> None:
    state = _active_state()
    blocked = evaluate_sync_upgrade(
        state, SyncUpgradeSignals(wants_continue=False, sync_extra_value=True)
    )
    assert blocked.eligible is False
    assert blocked.active_member_count == 2
    assert blocked.core_members_want_continue is False

    no_extra_value = evaluate_sync_upgrade(
        state, SyncUpgradeSignals(wants_continue=True, sync_extra_value=False)
    )
    assert no_extra_value.eligible is False
    assert no_extra_value.core_members_want_continue is True
    assert "额外价值" in no_extra_value.reason


def test_sync_upgrade_is_explainable_and_idempotent_after_start() -> None:
    state = _active_state()
    decision = evaluate_sync_upgrade(
        state,
        SyncUpgradeSignals(
            wants_continue=True,
            sync_extra_value=True,
            discussion_quality=True,
            external_attention=True,
            public_value=True,
        ),
    )
    assert decision.eligible is True
    assert decision.bonus_signals == ["当前讨论质量较高", "外围关注正在增加", "问题具有公共价值"]

    sync = state.model_copy(deep=True)
    sync.conversation.mode = ConversationMode.SYNC
    already = evaluate_sync_upgrade(
        sync, SyncUpgradeSignals(wants_continue=False, sync_extra_value=False)
    )
    assert already.eligible is True
    assert already.reason == "同步讨论已经开始"
