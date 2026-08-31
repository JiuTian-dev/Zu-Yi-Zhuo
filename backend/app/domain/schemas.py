from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, model_validator

from .enums import Action, DisagreementType, Level, Phase, SafetyLevel

Confidence = Annotated[float, Field(ge=0, le=1)]
TurnEvidence = Annotated[list[PositiveInt], Field(min_length=1)]
SafetyAction = Literal["allow", "pause", "intercept", "remove"]

class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class EvidenceStatement(ContractModel):
    text: str = Field(min_length=1)
    evidence_turns: TurnEvidence

class Disagreement(EvidenceStatement):
    disagreement_type: DisagreementType
    participant_ids: list[str] = Field(default_factory=list, min_length=1)

class RelevantExperience(ContractModel):
    text: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)

class ParticipantSeed(ContractModel):
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    declared_position: str = Field(min_length=1)
    relevant_experience: list[RelevantExperience] = Field(default_factory=list)


class MatchRequest(ContractModel):
    """Bounded candidate pool for the first-stage "find people" preview."""

    core_question: str = Field(min_length=1)
    candidates: list[ParticipantSeed] = Field(min_length=2, max_length=20)
    table_size: int = Field(default=4, ge=2, le=5)

    @model_validator(mode="after")
    def candidate_ids_are_unique_and_fit(self) -> "MatchRequest":
        ids = [candidate.participant_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate participant_id values must be unique")
        if self.table_size > len(self.candidates):
            raise ValueError("table_size cannot exceed candidates")
        return self


class MatchSeat(ContractModel):
    """Public seat preview; private profile fields are intentionally absent."""

    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)


class MatchReason(ContractModel):
    participant_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_terms: list[str] = Field(default_factory=list, max_length=5)


class MatchPlan(ContractModel):
    core_question: str = Field(min_length=1)
    selected: list[MatchSeat] = Field(min_length=2, max_length=5)
    reasons: list[MatchReason] = Field(min_length=2, max_length=5)
    unmatched_participant_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def selected_reasons_are_consistent(self) -> "MatchPlan":
        selected_ids = [seat.participant_id for seat in self.selected]
        reason_ids = [reason.participant_id for reason in self.reasons]
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("selected participant_id values must be unique")
        if len(reason_ids) != len(set(reason_ids)):
            raise ValueError("reason participant_id values must be unique")
        if len(self.unmatched_participant_ids) != len(set(self.unmatched_participant_ids)):
            raise ValueError("unmatched participant_id values must be unique")
        if set(reason_ids) != set(selected_ids):
            raise ValueError("reasons must cover exactly the selected participants")
        if set(selected_ids) & set(self.unmatched_participant_ids):
            raise ValueError("selected participants cannot be unmatched")
        return self

class HumanTurn(ContractModel):
    turn_id: PositiveInt
    participant_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SafetyDecision(ContractModel):
    """Deterministic pre-loop outcome for one untrusted human message."""

    blocked: bool
    action: SafetyAction
    level: SafetyLevel
    reason: str = Field(min_length=1)
    evidence_turns: list[PositiveInt] = Field(default_factory=list)

    @model_validator(mode="after")
    def action_matches_blocking_status(self) -> "SafetyDecision":
        if self.blocked and (self.action == "allow" or not self.evidence_turns):
            raise ValueError("blocked safety decisions require enforcement and turn evidence")
        if not self.blocked and self.action != "allow":
            raise ValueError("allowed safety decisions must use allow")
        return self

class OpenLoop(ContractModel):
    question: str = Field(min_length=1)
    priority: Level
    evidence_turns: TurnEvidence

class ParticipantState(ContractModel):
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    profile_shared: bool = False
    declared_position: str | None = Field(default=None, min_length=1)
    current_position: EvidenceStatement | None = None
    key_contributions: list[EvidenceStatement] = Field(default_factory=list)
    unused_relevant_experience: list[RelevantExperience] = Field(default_factory=list)
    engagement: Level
    last_spoke_turn: PositiveInt | None = None
    good_pass_opportunity: bool = False

class ConversationState(ContractModel):
    state: str = Field(min_length=1)
    most_promising_thread: EvidenceStatement | None = None
    risk_flags: list[EvidenceStatement] = Field(default_factory=list)
    safety_level: SafetyLevel
    closed: bool = False

class InterventionState(ContractModel):
    reasons_to_speak: list[EvidenceStatement] = Field(default_factory=list)
    reasons_to_stay_silent: list[EvidenceStatement] = Field(default_factory=list)
    recommended_action: Action = Action.SILENCE
    confidence: Confidence
    last_action: Action = Action.SILENCE
    last_agent_turn_id: str | None = None
    human_turns_since_last_intervention: int = Field(default=0, ge=0)

class TableState(ContractModel):
    table_id: str = Field(min_length=1)
    version: int = Field(ge=0)
    core_question: str = Field(min_length=1)
    current_subquestion: str | None = None
    phase: Phase
    momentum: Level
    close_readiness: Level
    new_insights: list[EvidenceStatement] = Field(default_factory=list, max_length=8)
    consensus: list[EvidenceStatement] = Field(default_factory=list, max_length=5)
    disagreements: list[Disagreement] = Field(default_factory=list)
    open_loops: list[OpenLoop] = Field(default_factory=list, max_length=3)
    participants: dict[str, ParticipantState] = Field(default_factory=dict)
    conversation: ConversationState
    intervention: InterventionState

    @model_validator(mode="after")
    def participant_keys_match_ids(self) -> "TableState":
        if any(key != participant.participant_id for key, participant in self.participants.items()):
            raise ValueError("participant map keys must match participant_id")
        if self.conversation.safety_level is SafetyLevel.CRITICAL and not self.conversation.risk_flags:
            raise ValueError("critical safety requires risk_flags with turn evidence")
        return self

class GateDecision(ContractModel):
    should_speak: bool = False
    safety_override: bool = False
    evidence_turns: list[PositiveInt] = Field(default_factory=list)
    reasons_to_speak: list[str] = Field(default_factory=list)
    reasons_to_stay_silent: list[str] = Field(default_factory=lambda: ["default silence"])
    confidence: Confidence = 1.0

    @model_validator(mode="after")
    def safety_requires_speech(self) -> "GateDecision":
        if self.safety_override and not self.should_speak:
            raise ValueError("safety_override requires should_speak")
        if self.should_speak and not self.reasons_to_speak:
            raise ValueError("speech decisions require reasons_to_speak")
        if not self.should_speak and not self.reasons_to_stay_silent:
            raise ValueError("silence decisions require reasons_to_stay_silent")
        return self

class RouteDecision(ContractModel):
    action: Action = Action.SILENCE
    target_participant_id: str | None = None
    evidence_turns: list[PositiveInt] = Field(default_factory=list)
    confidence: Confidence = 1.0

    @model_validator(mode="after")
    def action_has_evidence(self) -> "RouteDecision":
        if self.action != Action.SILENCE and not self.evidence_turns:
            raise ValueError("non-SILENCE routes require evidence_turns")
        if self.action == Action.PASS and self.target_participant_id is None:
            raise ValueError("PASS requires target_participant_id")
        return self

class AgentActionEvent(ContractModel):
    action: Action
    target_participant_id: str | None = None
    text: str | None = Field(default=None, max_length=120)
    visual_hint: dict[str, JsonValue]
    evidence_turns: list[PositiveInt] = Field(default_factory=list)
    state_version: int = Field(ge=0)
    confidence: Confidence

    @model_validator(mode="after")
    def action_has_required_context(self) -> "AgentActionEvent":
        if self.action == Action.SILENCE and self.text is not None:
            raise ValueError("SILENCE events must not have text")
        if self.action != Action.SILENCE and not self.text:
            raise ValueError("non-SILENCE actions require text")
        if self.action != Action.SILENCE and not self.evidence_turns:
            raise ValueError("non-SILENCE actions require evidence_turns")
        if self.action == Action.PASS and self.target_participant_id is None:
            raise ValueError("PASS requires target_participant_id")
        return self


class GroundingCard(ContractModel):
    """A trusted source excerpt that Host may place on the table."""

    title: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)

class TokenUsage(ContractModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class InterventionRecord(AgentActionEvent):
    intervention_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    reasons_to_speak: list[EvidenceStatement] = Field(default_factory=list)
    reasons_to_stay_silent: list[EvidenceStatement] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    model: str = Field(min_length=1)
    token_usage: TokenUsage
    outcome: EvidenceStatement | None = None
    reflection: EvidenceStatement | None = None


class RelationshipSuggestion(ContractModel):
    participant_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_turns: TurnEvidence


class FollowUpItem(ContractModel):
    item_type: Literal["suggestion", "commitment"]
    text: str = Field(min_length=1)
    is_commitment: bool
    owner_participant_id: str | None = None
    evidence_turns: TurnEvidence

    @model_validator(mode="after")
    def type_matches_commitment_flag(self) -> "FollowUpItem":
        if self.is_commitment != (self.item_type == "commitment"):
            raise ValueError("is_commitment must match item_type")
        if self.is_commitment and self.owner_participant_id is None:
            raise ValueError("commitments require owner_participant_id")
        return self


class ReflectionResult(ContractModel):
    """Effect log for an intervention after enough human turns have passed."""

    intervention_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    intervention_action: Action
    human_turns_observed: int = Field(ge=0)
    effective: bool
    score: Confidence
    confidence: Confidence
    effects: list[EvidenceStatement] = Field(default_factory=list)
    negative_effects: list[EvidenceStatement] = Field(default_factory=list)
    strategy_note: str = Field(min_length=1)


class SharedBaseline(ContractModel):
    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    core_question_before: str = Field(min_length=1)
    key_consensus: list[EvidenceStatement] = Field(default_factory=list, max_length=5)
    unresolved_disagreements: list[Disagreement] = Field(default_factory=list)
    evolved_question: EvidenceStatement
    collective_next_steps: list[FollowUpItem] = Field(default_factory=list)


class PersonalCard(ContractModel):
    table_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    what_changed: list[EvidenceStatement] = Field(default_factory=list)
    your_contribution: list[EvidenceStatement] = Field(default_factory=list)
    worth_continuing_with: list[RelationshipSuggestion] = Field(default_factory=list)
    suggested_next_actions: list[FollowUpItem] = Field(default_factory=list, max_length=3)
