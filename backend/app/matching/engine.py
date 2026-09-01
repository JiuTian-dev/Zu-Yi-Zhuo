"""Deterministic, bounded matching for a single table preview."""

from collections.abc import Iterable
import re

from app.domain import CandidateRecommendation, HumanTurn, InvitationPreference, Level, MatchPlan, MatchReason, MatchRequest, MatchSeat, ParticipantSeed, SafetyLevel, TableRecruitmentDecision, TableState

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-z0-9]{2,}")


def _terms(text: str) -> set[str]:
    """Extract stable Chinese bigrams plus ASCII words without external NLP."""
    result = {word.lower() for word in _WORD.findall(text.lower())}
    for chunk in _CJK.findall(text):
        result.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return result


def _profile_terms(candidate: ParticipantSeed) -> set[str]:
    pieces: Iterable[str] = (
        candidate.role,
        candidate.declared_position,
        *(experience.text for experience in candidate.relevant_experience),
    )
    return _terms(" ".join(pieces))


def infer_role_gaps(roles: Iterable[str]) -> list[str]:
    """Return bounded information-role gaps for an existing table."""
    text = " ".join(roles).lower()
    gaps: list[str] = []
    if not any(term in text for term in ("实践", "落地", "运营", "业务", "创业", "practitioner")):
        gaps.append("实践者")
    if not any(term in text for term in ("研究", "技术", "架构", "专家", "安全", "research", "engineer")):
        gaps.append("专业者")
    if not any(term in text for term in ("产品", "用户", "处境", "一线", "提问", "product", "user")):
        gaps.append("处境者")
    return gaps


def _recruitment_query(
    state: TableState,
    role_gaps: list[str],
    topic: str | None = None,
) -> str:
    topic = topic or state.current_subquestion or state.core_question
    suffix = f" {role_gaps[0]}" if role_gaps else ""
    return f"{topic}{suffix}"[:120]


def evaluate_recruitment_need(
    state: TableState,
    turns: Iterable[HumanTurn],
) -> TableRecruitmentDecision:
    """Explain whether a table needs another person without choosing or inviting one."""
    role_gaps = infer_role_gaps(person.role for person in state.participants.values())
    open_seats = max(0, 5 - len(state.participants))
    common = {"open_seats": open_seats, "role_gaps": role_gaps}

    if state.conversation.closed or state.conversation.soft_expired:
        return TableRecruitmentDecision(
            **common,
            should_recruit=False,
            trigger="table_unavailable",
            reason="桌已关闭或暂时过期，不再建议补位。",
        )
    if state.conversation.safety_level is SafetyLevel.CRITICAL:
        return TableRecruitmentDecision(
            **common,
            should_recruit=False,
            trigger="safety_paused",
            reason="桌处于安全暂停状态，应先完成安全处置。",
        )
    if open_seats == 0:
        return TableRecruitmentDecision(
            **common,
            should_recruit=False,
            trigger="table_full",
            reason="桌已达到五位真人上限。",
        )
    if len(state.participants) < 4:
        return TableRecruitmentDecision(
            **common,
            should_recruit=True,
            trigger="below_minimum",
            reason="当前少于四位真人，建议补足基本开桌人数。",
            suggested_query=_recruitment_query(state, role_gaps),
        )

    high_loops = [item for item in state.open_loops if item.priority is Level.HIGH]
    if not high_loops:
        return TableRecruitmentDecision(
            **common,
            should_recruit=False,
            trigger="wait_for_discussion",
            reason="已有四位真人，但讨论尚未形成有充分证据的关键缺口。",
        )

    turn_by_id = {turn.turn_id: turn for turn in turns}
    supported_loop = None
    supported_evidence: list[int] = []
    first_evidence: list[int] = []
    for open_loop in high_loops:
        valid_evidence = sorted({
            turn_id for turn_id in open_loop.evidence_turns if turn_id in turn_by_id
        })
        if not first_evidence:
            first_evidence = valid_evidence[:10]
        speakers = {turn_by_id[turn_id].participant_id for turn_id in valid_evidence}
        if len(valid_evidence) >= 2 and len(speakers) >= 2:
            supported_loop = open_loop
            supported_evidence = valid_evidence[:10]
            break
    if supported_loop is None:
        return TableRecruitmentDecision(
            **common,
            should_recruit=False,
            trigger="wait_for_discussion",
            reason="关键缺口还没有得到至少两位真人的讨论证据支持。",
            evidence_turns=first_evidence,
        )
    if not role_gaps:
        return TableRecruitmentDecision(
            **common,
            should_recruit=False,
            trigger="composition_sufficient",
            reason="讨论已有真实分歧证据，但当前信息角色结构已经足够。",
            evidence_turns=supported_evidence,
        )
    return TableRecruitmentDecision(
        **common,
        should_recruit=True,
        trigger="live_role_gap",
        reason=f"真实讨论暴露出关键未决问题，当前最缺{role_gaps[0]}视角。",
        evidence_turns=supported_evidence,
        suggested_query=_recruitment_query(state, role_gaps, supported_loop.question),
    )


def _candidate_value(candidate: ParticipantSeed, question_terms: set[str]) -> tuple[int, int, str]:
    overlap = len(_profile_terms(candidate) & question_terms)
    return overlap, int(bool(candidate.relevant_experience)), candidate.participant_id


def build_match_plan(request: MatchRequest) -> MatchPlan:
    """Select a varied, evidence-backed group without exposing private profile data."""
    question_terms = _terms(request.core_question)
    remaining = [
        candidate
        for candidate in request.candidates
        if candidate.roundtable_invite_preference is not InvitationPreference.NONE
    ]
    selected: list[ParticipantSeed] = []
    selected_roles: set[str] = set()

    while remaining and len(selected) < request.table_size:
        def value(candidate: ParticipantSeed) -> tuple[int, int, int, str]:
            terms = _profile_terms(candidate)
            new_terms = len((terms & question_terms) - set().union(*(_profile_terms(item) for item in selected)))
            role_bonus = int(candidate.role not in selected_roles)
            overlap, experience, _ = _candidate_value(candidate, question_terms)
            return new_terms, role_bonus, overlap + experience, candidate.participant_id

        choice = max(remaining, key=value)
        selected.append(choice)
        selected_roles.add(choice.role)
        remaining.remove(choice)

    selected_ids = {candidate.participant_id for candidate in selected}
    seats = [MatchSeat(
        participant_id=candidate.participant_id,
        display_name=candidate.display_name,
        role=candidate.role,
    ) for candidate in selected]
    reasons = []
    for candidate in selected:
        # Private position/experience may influence selection, but never leaves
        # the service in a public match explanation before consent.
        overlap = sorted(_terms(candidate.role) & question_terms)[:5]
        if overlap:
            reason = f"带来{candidate.role}视角，和问题有直接交集"
        else:
            reason = f"补充{candidate.role}视角，避免一桌只有同一种经验"
        reasons.append(MatchReason(
            participant_id=candidate.participant_id,
            reason=reason,
            evidence_terms=overlap,
            evidence_signal_ids=candidate.public_signal_ids[:5],
        ))
    return MatchPlan(
        core_question=request.core_question,
        selected=seats,
        reasons=reasons,
        unmatched_participant_ids=[
            candidate.participant_id for candidate in request.candidates
            if candidate.participant_id not in selected_ids
        ],
    )


def recommend_candidates(
    state: TableState,
    candidates: Iterable[ParticipantSeed],
    limit: int,
) -> list[CandidateRecommendation]:
    """Rank source candidates for a table gap without mutating the table."""
    if limit <= 0:
        raise ValueError("candidate recommendation limit must be positive")
    question_terms = _terms(state.core_question)
    existing_roles = {person.role for person in state.participants.values()}
    role_gaps = infer_role_gaps(existing_roles)
    remaining: list[ParticipantSeed] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        if candidate.participant_id in state.participants:
            continue
        if candidate.participant_id in seen_ids:
            raise ValueError("candidate participant_id values must be unique")
        seen_ids.add(candidate.participant_id)
        if candidate.roundtable_invite_preference is InvitationPreference.NONE:
            continue
        remaining.append(candidate)

    def value(candidate: ParticipantSeed) -> tuple[int, int, int, int, str]:
        terms = _profile_terms(candidate)
        gap_bonus = int(any(
            gap == "实践者" and any(term in candidate.role.lower() for term in ("实践", "落地", "运营", "业务", "创业"))
            or gap == "专业者" and any(term in candidate.role.lower() for term in ("研究", "技术", "架构", "专家", "安全"))
            or gap == "处境者" and any(term in candidate.role.lower() for term in ("产品", "用户", "一线", "提问"))
            for gap in role_gaps
        ))
        return (
            gap_bonus,
            int(candidate.role not in existing_roles),
            len(terms & question_terms),
            int(bool(candidate.relevant_experience)),
            candidate.participant_id,
        )

    ranked = sorted(remaining, key=value, reverse=True)[:limit]
    recommendations: list[CandidateRecommendation] = []
    for candidate in ranked:
        overlap = sorted(_terms(candidate.role) & question_terms)[:5]
        if candidate.role not in existing_roles and role_gaps:
            reason = f"当前桌缺少这一类角色，补充{candidate.role}视角"
        elif overlap:
            reason = f"带来{candidate.role}视角，和桌面问题有直接交集"
        else:
            reason = f"补充{candidate.role}视角，避免桌内经验同质化"
        recommendations.append(CandidateRecommendation(
            participant_id=candidate.participant_id,
            display_name=candidate.display_name,
            role=candidate.role,
            reason=reason,
            evidence_terms=overlap,
            evidence_signal_ids=candidate.public_signal_ids[:5],
        ))
    return recommendations
