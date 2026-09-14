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
            "AI 时代，专业判断会被替代吗？",
            (
                _seed(
                    "judgment-engineer",
                    "周砚",
                    "AI 工程师 · 技术视角",
                    "AI 会替代可标准化的判断，但不能替代责任主体",
                    "参与过企业知识助手从试点到上线的评估与复盘",
                ),
                _seed(
                    "judgment-doctor",
                    "林夏",
                    "临床医生 · 经验视角",
                    "高风险专业判断来自现场经验，也来自愿意承担后果",
                    "在临床辅助决策中持续核对模型建议与真实病情",
                ),
                _seed(
                    "judgment-researcher",
                    "程野",
                    "认知研究者 · 理论视角",
                    "专业判断不是答案本身，而是一套可解释、可质疑的过程",
                    "研究过专家直觉、规则系统与生成式 AI 的判断边界",
                ),
                _seed(
                    "judgment-auditor",
                    "秦越",
                    "风控负责人 · 事实视角",
                    "判断是否可靠，要回到证据、误差和可以追责的记录",
                    "负责过自动化决策系统上线前后的风险审查",
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
