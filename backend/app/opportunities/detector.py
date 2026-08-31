"""Deterministic opportunity discovery from authorized public content signals."""

from collections import defaultdict
import re

from app.domain import ContentSignal, OpportunityPreview, OpportunityRequest, ParticipantSeed
from app.domain.schemas import RelevantExperience, SourceEvidence


_TAG = re.compile(r"<[^>]+>")


def _compact(text: str, limit: int = 240) -> str:
    value = _TAG.sub("", text).replace("\n", " ").strip()
    return value if len(value) <= limit else f"{value[:limit - 1].rstrip()}…"


def _role_gaps(signals: list[ContentSignal]) -> list[str]:
    roles = " ".join(signal.author_role or "" for signal in signals).lower()
    gaps: list[str] = []
    if not any(term in roles for term in ("实践", "落地", "运营", "业务", "创业", "practitioner")):
        gaps.append("实践者")
    if not any(term in roles for term in ("研究", "技术", "架构", "专家", "安全", "research", "engineer")):
        gaps.append("专业者")
    if not any(term in roles for term in ("产品", "用户", "处境", "一线", "提问", "product", "user")):
        gaps.append("处境者")
    return gaps


def _candidate_seeds(signals: list[ContentSignal]) -> list[ParticipantSeed]:
    grouped: dict[str, list[ContentSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.author_id].append(signal)
    result: list[ParticipantSeed] = []
    for author_id in sorted(grouped):
        author_signals = sorted(grouped[author_id], key=lambda item: (-item.engagement, item.signal_id))
        first = author_signals[0]
        experience: list[RelevantExperience] = []
        seen_refs: set[str] = set()
        for signal in author_signals:
            if signal.source_ref in seen_refs:
                continue
            seen_refs.add(signal.source_ref)
            experience.append(
                RelevantExperience(text=_compact(signal.excerpt), source_ref=signal.source_ref)
            )
            if len(experience) == 3:
                break
        result.append(ParticipantSeed(
            participant_id=author_id,
            display_name=first.author_name,
            role=first.author_role or "讨论参与者",
            declared_position=first.public_stance or "围绕该问题提供公开观点",
            relevant_experience=experience,
            public_signal_ids=[signal.signal_id for signal in author_signals[:20]],
        ))
    return result


def build_opportunity_preview(request: OpportunityRequest) -> OpportunityPreview:
    """Find explainable signs that public content still needs a live exchange."""
    signals = list(request.signals)
    signal_ids = [signal.signal_id for signal in signals]
    unfinishedness = [SourceEvidence(
        text="已有不同作者围绕同一问题表达，值得直接交换经验",
        signal_ids=signal_ids,
    )]
    content_types = {signal.content_type for signal in signals}
    if len(content_types) > 1:
        unfinishedness.append(SourceEvidence(
            text="问题与回答或文章同时出现，现有内容尚未收敛为一个可直接复用的结论",
            signal_ids=[signal.signal_id for signal in signals if signal.content_type != "question"],
        ))
    stances = {signal.public_stance.strip() for signal in signals if signal.public_stance}
    if len(stances) > 1:
        unfinishedness.append(SourceEvidence(
            text="公开立场存在差异，需要让不同判断在同桌中对话",
            signal_ids=[signal.signal_id for signal in signals if signal.public_stance],
        ))
    authors = len({signal.author_id for signal in signals})
    confidence = round(min(
        0.95,
        0.35
        + 0.1 * min(authors - 1, 3)
        + 0.1 * int(len(content_types) > 1)
        + 0.1 * int(len(stances) > 1)
        + 0.1 * int("answer" in content_types),
    ), 2)
    return OpportunityPreview(
        core_question=request.query.strip(),
        signal_ids=signal_ids,
        unfinishedness=unfinishedness[:3],
        role_gaps=_role_gaps(signals),
        candidates=_candidate_seeds(signals),
        confidence=confidence,
    )


__all__ = ("build_opportunity_preview",)
