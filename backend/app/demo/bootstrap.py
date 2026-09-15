"""Repeatable local demo data for the multi-table product journey."""

from dataclasses import asdict, dataclass
from typing import Literal

from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed, TableState

from .scenarios import flagship_participants

DemoSeedStatus = Literal["created", "existing"]


@dataclass(frozen=True)
class DemoSeedResult:
    """One deterministic seed result suitable for CLI JSON output."""

    table_id: str
    status: DemoSeedStatus
    participant_count: int
    state_version: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _seed(
    participant_id: str,
    display_name: str,
    role: str,
    declared_position: str,
    experience: str,
) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=display_name,
        role=role,
        declared_position=declared_position,
        relevant_experience=[
            {"text": experience, "source_ref": f"demo:{participant_id}:experience"}
        ],
    )


def _demo_table_specs() -> tuple[tuple[str, str, tuple[ParticipantSeed, ...]], ...]:
    return (
        (
            "demo-agent",
            "离开大城市，是逃避还是重新选择生活？",
            (
                _seed(
                    "judgment-engineer",
                    "周砚",
                    "产品工程师 · 机会视角",
                    "城市不只是压力，也是一张由工作、朋友和信息组成的机会网络",
                    "认真尝试过半年远程工作，重新理解了线下关系与机会的价值",
                ),
                _seed(
                    "judgment-doctor",
                    "林夏",
                    "县城医生 · 亲历视角",
                    "离开不是退场，而是把有限时间重新分配给想负责的人和事",
                    "从上海回到家乡工作三年，经历过获得陪伴与失去平台的双重变化",
                ),
                _seed(
                    "judgment-researcher",
                    "程野",
                    "城市研究者 · 结构视角",
                    "走还是留既是个人选择，也受住房、照护和公共服务共同塑造",
                    "访谈过在大城市与家乡之间反复迁移的年轻人",
                ),
                _seed(
                    "judgment-auditor",
                    "秦越",
                    "社区营造者 · 关系视角",
                    "生活质量也取决于能否建立稳定、互相照应的关系",
                    "参与过青年共居与社区活动的长期运营",
                ),
            ),
        ),
        (
            "demo-rest",
            "为什么我们越来越不会休息？",
            (
                _seed(
                    "rest-practitioner",
                    "沈知遥",
                    "实践者",
                    "休息不是奖励，而是生活的默认状态",
                    "试过把三天空出来，却发现自己仍然被产出焦虑追着走",
                ),
                _seed(
                    "rest-researcher",
                    "周默",
                    "专业者",
                    "我们把价值感过度绑定在持续产出上",
                    "长期研究工作节奏与注意力恢复之间的关系",
                ),
                _seed(
                    "rest-context",
                    "林舟",
                    "处境者",
                    "自由职业让下班和休息都失去了边界",
                    "从自由职业切换到远程团队后重新建立工作边界",
                ),
                _seed(
                    "rest-product",
                    "许晴",
                    "产品负责人",
                    "真正的难题是停下来时不知道自己是谁",
                    "负责过一款帮助团队建立健康工作节奏的产品试点",
                ),
            ),
        ),
        (
            "demo-gap",
            "AI Agent 真正进入企业，卡住的是技术还是采购？",
            tuple(flagship_participants[:2]),
        ),
    )


def seed_demo_tables(repository: InMemoryTableRepository) -> list[DemoSeedResult]:
    """Create the three local demo tables without overwriting existing state."""
    results: list[DemoSeedResult] = []
    for table_id, core_question, participants in _demo_table_specs():
        try:
            state = repository.get(table_id)
            seed_status: DemoSeedStatus = "existing"
        except KeyError:
            state = repository.create(table_id, core_question, participants)
            seed_status = "created"
        results.append(
            DemoSeedResult(
                table_id=table_id,
                status=seed_status,
                participant_count=len(state.participants),
                state_version=state.version,
            )
        )
    return results


__all__ = ("DemoSeedResult", "seed_demo_tables")
