from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, model_validator

from .enums import Action, DisagreementType, Level, Phase, SafetyLevel

Confidence = Annotated[float, Field(ge=0, le=1)]
TurnEvidence = Annotated[list[PositiveInt], Field(min_length=1)]

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

class HumanTurn(ContractModel):
    turn_id: PositiveInt
    participant_id: str = Field(min_length=1)
    text: str = Field(min_length=1)

class OpenLoop(ContractModel):
    question: str = Field(min_length=1)
    priority: Level
    evidence_turns: TurnEvidence

class ParticipantState(ContractModel):
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
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
        if self.action != Action.SILENCE and not self.evidence_turns:
            raise ValueError("non-SILENCE actions require evidence_turns")
        if self.action == Action.PASS and self.target_participant_id is None:
            raise ValueError("PASS requires target_participant_id")
        return self

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
