"""First-track judge demo data.

The visible participants and turns are deliberately labelled as placeholders.
Replace them with consented contributions from real collaborators before the
submission video; the seed only keeps the product journey runnable when no one
else is online during judging.
"""

from dataclasses import dataclass

from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed, TableState


TRACK_ONE_TABLE_ID = "track-one-human-connection"


@dataclass(frozen=True)
class TrackOneSeedResult:
    table_id: str
    status: str
    participant_count: int
    turn_count: int
    state_version: int


def _participant(
    participant_id: str,
    display_name: str,
    role: str,
    position: str,
    experience: str,
) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=display_name,
        role=f"{role} · 演示占位",
        declared_position=position,
        relevant_experience=[
            {
                "text": experience,
                "source_ref": f"local-demo-placeholder:{participant_id}",
            }
        ],
    )


_PARTICIPANTS = (
    _participant(
        "track-one-product",
        "共创者 A",
        "产品工程师 · 机会视角",
        "城市不只是压力，也是一张由工作、朋友和信息组成的机会网络",
        "尝试过半年远程工作，重新理解了线下关系与机会的价值",
    ),
    _participant(
        "track-one-creator",
        "共创者 B",
        "县城医生 · 亲历视角",
        "离开不是退场，而是把有限时间重新分配给想负责的人和事",
        "从上海回到家乡工作三年，经历了获得陪伴与失去平台的双重变化",
    ),
    _participant(
        "track-one-newcomer",
        "共创者 C",
        "城市研究者 · 结构视角",
        "走还是留既是个人选择，也受住房、照护与公共服务共同塑造",
        "访谈过在大城市和家乡之间反复迁移的年轻人",
    ),
)

_TURNS = (
    (
        "track-one-turn-1",
        "track-one-product",
        "我尝试过半年远程工作，才发现城市给我的不只是一份工作，还有朋友和偶然发生的机会。也许可以先试住，而不是把走留变成一次豪赌。",
    ),
    (
        "track-one-turn-2",
        "track-one-creator",
        "我从上海回到家乡三年。收入和平台的确变小，但第一次能稳定陪家人。离开不是答案，它只是让我看清自己愿意交换什么。",
    ),
    (
        "track-one-turn-3",
        "track-one-newcomer",
        "把离开解释成勇敢或逃避都太简单。住房、照护、伴侣和职业阶段，会让同一个人在不同时间作出不同选择。",
    ),
    (
        "track-one-turn-4",
        "track-one-product",
        "如果工作和关系能够迁移，目标生活也足够具体，我会支持离开；如果只是被一次挫折推动，我更愿意先做低成本试验。",
    ),
    (
        "track-one-turn-5",
        "track-one-creator",
        "所以真正的问题不是走还是留，而是你真正想离开的，是城市，还是一种失去掌控的生活。",
    ),
)


def seed_track_one_demo(repository: InMemoryTableRepository) -> TrackOneSeedResult:
    """Idempotently seed one three-human asynchronous table for track one."""
    try:
        state = repository.get(TRACK_ONE_TABLE_ID)
        status = "existing"
    except KeyError:
        state = repository.create(
            TRACK_ONE_TABLE_ID,
            "离开大城市，是逃避还是重新选择生活？",
            _PARTICIPANTS,
        )
        status = "created"

    if not state.conversation.closed and not state.conversation.soft_expired:
        for message_id, participant_id, text in _TURNS:
            state, _ = repository.append_message_once(
                TRACK_ONE_TABLE_ID,
                participant_id,
                text,
                message_id,
            )

    return TrackOneSeedResult(
        table_id=TRACK_ONE_TABLE_ID,
        status=status,
        participant_count=len(state.participants),
        turn_count=len(repository.turns(TRACK_ONE_TABLE_ID)),
        state_version=state.version,
    )


__all__ = ("TRACK_ONE_TABLE_ID", "TrackOneSeedResult", "seed_track_one_demo")
