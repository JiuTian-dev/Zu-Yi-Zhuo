from app.api.repository import InMemoryTableRepository
from app.demo.track_one import TRACK_ONE_TABLE_ID, seed_track_one_demo


def test_track_one_demo_is_idempotent_and_leaves_one_human_seat() -> None:
    repository = InMemoryTableRepository()

    first = seed_track_one_demo(repository)
    second = seed_track_one_demo(repository)

    assert first.status == "created"
    assert second.status == "existing"
    assert first.participant_count == 3
    assert first.turn_count == 5
    assert second.turn_count == 5
    assert repository.get(TRACK_ONE_TABLE_ID).core_question == (
        "离开大城市，是逃避还是重新选择生活？"
    )
    assert all("演示占位" in participant.role for participant in repository.get(TRACK_ONE_TABLE_ID).participants.values())
    assert [turn.message_id for turn in repository.turns(TRACK_ONE_TABLE_ID)] == [
        f"track-one-turn-{index}" for index in range(1, 6)
    ]
