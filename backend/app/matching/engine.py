"""Deterministic, bounded matching for a single table preview."""

from collections.abc import Iterable
import re

from app.domain import InvitationPreference, MatchPlan, MatchReason, MatchRequest, MatchSeat, ParticipantSeed

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
