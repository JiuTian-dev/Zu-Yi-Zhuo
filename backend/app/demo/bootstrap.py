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
            "AI Agent 真正进入企业，卡住的是技术还是采购？",
            tuple(flagship_participants[:4]),
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
            "AI 时代，专业判断会被替代吗？",
            (
                _seed(
                    "gap-product",
                    "方宁",
                    "产品负责人",
                    "判断不能只看模型分数，还要看真实使用场景",
                    "负责过面向真实用户的 AI 产品试点",
                ),
                _seed(
                    "gap-architect",
                    "顾远",
                    "专业者",
                    "模型能力越强，边界和责任越需要被说清楚",
                    "参与过企业 AI 系统的架构与评审",
                ),
            ),
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
