from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, model_validator

from .enums import Action, ConversationMode, DisagreementType, InvitationPreference, InvitationStatus, Level, Phase, SafetyLevel

Confidence = Annotated[float, Field(ge=0, le=1)]
TurnEvidence = Annotated[list[PositiveInt], Field(min_length=1)]
SafetyAction = Literal["allow", "pause", "intercept", "remove"]
SafetyResolutionAction = Literal["resume", "remove_participant"]

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
    roundtable_invite_preference: InvitationPreference = InvitationPreference.FEW
    # Public opportunity provenance only; private profile sources stay in
    # relevant_experience and are never copied into match explanations.
    public_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )


class ContentSignal(ContractModel):
    """An authorized public Zhihu signal used only for opportunity discovery."""

    signal_id: str = Field(min_length=1)
    content_type: Literal["question", "answer", "article"]
    title: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=1000)
    source_ref: str = Field(min_length=1)
    author_id: str = Field(min_length=1)
    author_name: str = Field(min_length=1, max_length=120)
    author_role: str | None = Field(default=None, min_length=1, max_length=80)
    public_stance: str | None = Field(default=None, min_length=1, max_length=240)
    engagement: int = Field(default=0, ge=0)
    visibility: Literal["public"] = "public"


class PersonalContextSignal(ContractModel):
    """A private, viewer-owned signal returned by an authorized personal source."""

    signal_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    content_type: Literal["question", "answer", "article", "follow", "favorite"]
    title: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=1000)
    source_ref: str = Field(min_length=1)
    private_stance: str | None = Field(default=None, min_length=1, max_length=240)
    visibility: Literal["private"] = "private"


PersonalContextScope = Literal["profile", "follows", "favorites", "public_content"]


class PersonalContextConsent(ContractModel):
    """A viewer-owned allowlist of personal-context scopes."""

    viewer_id: str = Field(min_length=1)
    scopes: list[PersonalContextScope] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def scopes_are_unique(self) -> "PersonalContextConsent":
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError("personal context scopes must be unique")
        return self


class PersonalContextPreview(ContractModel):
    """Ephemeral private themes derived from one viewer's authorized signals."""

    viewer_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=120)
    signals: list[PersonalContextSignal] = Field(default_factory=list, max_length=20)
    themes: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def signals_belong_to_viewer(self) -> "PersonalContextPreview":
        signal_ids = [signal.signal_id for signal in self.signals]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("personal signal_id values must be unique")
        if any(signal.owner_id != self.viewer_id for signal in self.signals):
            raise ValueError("personal signals must belong to viewer_id")
        return self


class OpportunityRequest(ContractModel):
    """Bounded public signals for the first-stage opportunity detector."""

    query: str = Field(min_length=1, max_length=120)
    signals: list[ContentSignal] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def signal_ids_and_authors_are_sufficient(self) -> "OpportunityRequest":
        signal_ids = [signal.signal_id for signal in self.signals]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("signal_id values must be unique")
        if len({signal.author_id for signal in self.signals}) < 2:
            raise ValueError("opportunity signals must cover at least two authors")
        return self


class ActiveIntentRequest(ContractModel):
    """A viewer's bounded natural-language request for a roundtable."""

    message: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=5)

    @model_validator(mode="after")
    def message_is_not_blank(self) -> "ActiveIntentRequest":
        if not self.message.strip():
            raise ValueError("active intent message must not be blank")
        return self


class ActiveIntentTableCandidate(ContractModel):
    """A public table that may satisfy an active intent."""

    table_id: str = Field(min_length=1)
    core_question: str = Field(min_length=1, max_length=120)
    current_subquestion: str | None = Field(default=None, max_length=120)
    mode: ConversationMode
    participant_count: int = Field(ge=0, le=5)
    available_seats: int = Field(ge=0, le=5)
    reason: str = Field(min_length=1, max_length=240)
    origin_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )


class ActiveIntentPreview(ContractModel):
    """Non-persistent route preview for the product's active-demand entry."""

    normalized_question: str = Field(min_length=1, max_length=120)
    route: Literal["clarify", "join_existing", "new_table"]
    clarifying_question: str | None = Field(default=None, max_length=120)
    candidates: list[ActiveIntentTableCandidate] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def route_has_consistent_payload(self) -> "ActiveIntentPreview":
        if self.route == "clarify" and (self.candidates or not self.clarifying_question):
            raise ValueError("clarify route requires a clarifying question and no candidates")
        if self.route == "join_existing" and not self.candidates:
            raise ValueError("join_existing route requires candidates")
        if self.route != "clarify" and self.clarifying_question is not None:
            raise ValueError("clarifying_question is only valid for clarify route")
        return self


class LobbyMemberView(ContractModel):
    """Public member summary shown before entering a table."""

    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)


class LobbyPreview(ContractModel):
    """Bounded, redacted pre-entry view of one conversation table."""

    table_id: str = Field(min_length=1)
    core_question: str = Field(min_length=1)
    current_subquestion: str | None = None
    phase: Phase
    mode: ConversationMode
    status: Literal["open", "soft_expired", "closed"]
    state_version: int = Field(ge=0)
    participant_count: int = Field(ge=0, le=5)
    available_seats: int = Field(ge=0, le=5)
    members: list[LobbyMemberView] = Field(default_factory=list, max_length=5)
    role_gaps: list[str] = Field(default_factory=list, max_length=5)
    missing_perspective: str = Field(min_length=1, max_length=240)
    origin_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )

    @model_validator(mode="after")
    def member_counts_are_consistent(self) -> "LobbyPreview":
        member_ids = [member.participant_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("lobby member participant_id values must be unique")
        if len(self.members) != self.participant_count:
            raise ValueError("lobby member count must match participant_count")
        if self.available_seats != 5 - self.participant_count:
            raise ValueError("lobby available_seats must match the five-seat cap")
        return self


class LobbyFitPreview(ContractModel):
    """Candidate-scoped, non-persistent explanation for a possible seat."""

    table_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    eligible: bool
    matched_role_gap: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def matched_gap_requires_eligibility(self) -> "LobbyFitPreview":
        if self.matched_role_gap is not None and not self.eligible:
            raise ValueError("ineligible fit previews must not expose a matched role gap")
        return self


class SourceEvidence(ContractModel):
    """Evidence that points back to source signals rather than chat turns."""

    text: str = Field(min_length=1, max_length=240)
    signal_ids: list[str] = Field(min_length=1, max_length=20)


class OpportunityPreview(ContractModel):
    """Explainable opportunity candidate before any table is created."""

    core_question: str = Field(min_length=1, max_length=120)
    signal_ids: list[str] = Field(min_length=2, max_length=20)
    # Public-only source projection for immediate explanation. This is a
    # preview artifact, not part of persisted TableState.
    source_signals: list[ContentSignal] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )
    unfinishedness: list[SourceEvidence] = Field(min_length=1, max_length=3)
    role_gaps: list[str] = Field(default_factory=list, max_length=5)
    candidates: list[ParticipantSeed] = Field(min_length=2, max_length=20)
    confidence: Confidence


class JoinRequest(ContractModel):
    """A candidate's request to be considered for an existing table."""

    request_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    candidate: ParticipantSeed
    message: str | None = Field(default=None, min_length=1, max_length=240)
    status: Literal["pending", "invited", "declined"] = "pending"
    invitation_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def invitation_state_is_consistent(self) -> "JoinRequest":
        if self.status == "invited" and self.invitation_id is None:
            raise ValueError("invited join requests require invitation_id")
        if self.status != "invited" and self.invitation_id is not None:
            raise ValueError("only invited join requests may reference an invitation")
        return self


class JoinRequestView(ContractModel):
    """Redacted join-request projection safe for candidates and table members."""

    request_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    message: str | None = Field(default=None, min_length=1, max_length=240)
    status: Literal["pending", "invited", "declined"]
    invitation_id: str | None = Field(default=None, min_length=1)


class Invitation(ContractModel):
    """Private persisted invitation; public APIs must project it to InvitationView."""

    invitation_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    inviter_id: str = Field(min_length=1)
    candidate: ParticipantSeed
    reason: str = Field(min_length=1, max_length=240)
    status: InvitationStatus = InvitationStatus.PENDING

    @model_validator(mode="after")
    def candidate_is_not_inviter(self) -> "Invitation":
        if self.candidate.participant_id == self.inviter_id:
            raise ValueError("invitation candidate must differ from inviter")
        return self


class InvitationView(ContractModel):
    """Redacted invitation projection safe for a candidate-facing response."""

    invitation_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)
    status: InvitationStatus


class SyncUpgradeSignals(ContractModel):
    """Self-reported signals used to preview a table's sync upgrade."""

    wants_continue: bool
    sync_extra_value: bool
    discussion_quality: bool = False
    external_attention: bool = False
    public_value: bool = False


class SyncUpgradeDecision(ContractModel):
    eligible: bool
    core_members_want_continue: bool
    sync_has_extra_value: bool
    active_member_count: int = Field(ge=0)
    bonus_signals: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=1, max_length=240)


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
        eligible = sum(
            candidate.roundtable_invite_preference is not InvitationPreference.NONE
            for candidate in self.candidates
        )
        if self.table_size > eligible:
            raise ValueError("table_size cannot exceed invitation-eligible candidates")
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
    evidence_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=5,
        exclude_if=lambda value: not value,
    )


class CandidateRecommendation(ContractModel):
    """Public, non-binding recommendation for a missing table seat."""

    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)
    evidence_terms: list[str] = Field(default_factory=list, max_length=5)
    evidence_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=5,
        exclude_if=lambda value: not value,
    )


class TableCandidatePreview(ContractModel):
    """Current table gap plus source-backed candidate recommendations."""

    table_id: str = Field(min_length=1)
    core_question: str = Field(min_length=1)
    open_seats: int = Field(ge=1, le=5)
    role_gaps: list[str] = Field(default_factory=list, max_length=5)
    candidates: list[CandidateRecommendation] = Field(default_factory=list, max_length=20)


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
    # Optional for legacy CLI/persistence records; WebSocket messages always set it.
    message_id: str | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)
    # When a core member explicitly promotes an external comment, retain the
    # immutable source reference without changing normal human-message shape.
    source_comment_id: str | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)


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


class SafetyResolution(ContractModel):
    """Immutable moderator outcome for one critical safety pause."""

    resolution_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    action: SafetyResolutionAction
    moderator_id: str = Field(min_length=1)
    participant_id: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1, max_length=240)
    from_state_version: int = Field(ge=0)
    state_version: int = Field(ge=0)

    @model_validator(mode="after")
    def action_target_matches(self) -> "SafetyResolution":
        if self.action == "remove_participant" and self.participant_id is None:
            raise ValueError("remove_participant requires participant_id")
        if self.action == "resume" and self.participant_id is not None:
            raise ValueError("resume must not include participant_id")
        if self.state_version <= self.from_state_version:
            raise ValueError("safety resolution must advance the table state")
        return self

class OpenLoop(ContractModel):
    question: str = Field(min_length=1)
    priority: Level
    evidence_turns: TurnEvidence

class ParticipantState(ContractModel):
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    roundtable_invite_preference: InvitationPreference = InvitationPreference.FEW
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
    mode: ConversationMode = ConversationMode.ASYNC
    closed: bool = False
    soft_expired: bool = False
    soft_expiry_reason: str | None = Field(default=None, min_length=1, max_length=240)

class InterventionState(ContractModel):
    reasons_to_speak: list[EvidenceStatement] = Field(default_factory=list)
    reasons_to_stay_silent: list[EvidenceStatement] = Field(default_factory=list)
    recommended_action: Action = Action.SILENCE
    confidence: Confidence
    last_action: Action = Action.SILENCE
    last_agent_turn_id: str | None = None
    human_turns_since_last_intervention: int = Field(default=0, ge=0)


class AgentPresence(ContractModel):
    """Stable public identity for the roundtable's non-human seat."""

    agent_id: str = Field(default="roundtable-agent", min_length=1)
    display_name: str = Field(default="圆桌 Agent", min_length=1, max_length=120)
    role: str = Field(default="对话搭档", min_length=1, max_length=120)
    status: Literal["active", "paused", "closed"] = "active"


class TableState(ContractModel):
    table_id: str = Field(min_length=1)
    origin_table_id: str | None = Field(default=None, min_length=1)
    # Public opportunity provenance only; private profile fields and source
    # payloads are intentionally not persisted in table state.
    origin_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )
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
    agent: AgentPresence = Field(default_factory=AgentPresence)

    @model_validator(mode="after")
    def participant_keys_match_ids(self) -> "TableState":
        if any(key != participant.participant_id for key, participant in self.participants.items()):
            raise ValueError("participant map keys must match participant_id")
        if self.origin_table_id == self.table_id:
            raise ValueError("origin_table_id must differ from table_id")
        if len(self.origin_signal_ids) != len(set(self.origin_signal_ids)):
            raise ValueError("origin_signal_ids must be unique")
        if self.conversation.safety_level is SafetyLevel.CRITICAL and not self.conversation.risk_flags:
            raise ValueError("critical safety requires risk_flags with turn evidence")
        if self.conversation.soft_expired and self.conversation.state not in {"soft_expired", "closed"}:
            raise ValueError("soft-expired conversations must use soft_expired or closed state")
        if self.conversation.state == "soft_expired" and not self.conversation.soft_expired:
            raise ValueError("soft_expired state requires soft_expired flag")
        if self.conversation.closed:
            self.agent.status = "closed"
        elif self.conversation.soft_expired or self.conversation.safety_level.value == "critical":
            self.agent.status = "paused"
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

    @model_validator(mode="after")
    def action_must_be_intervention(self) -> "InterventionRecord":
        if self.action is Action.SILENCE:
            raise ValueError("SILENCE actions do not create intervention records")
        return self


class RelationshipSuggestion(ContractModel):
    participant_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_turns: TurnEvidence


class RelationshipMemory(ContractModel):
    """A read-only reminder derived from one participant's closed-table evidence."""

    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    core_question: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)
    evidence_turns: TurnEvidence


class NoMatchPreference(ContractModel):
    """A participant's self-scoped preference not to be matched with another participant."""

    participant_id: str = Field(min_length=1)
    blocked_participant_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def participants_must_differ(self) -> "NoMatchPreference":
        if self.participant_id == self.blocked_participant_id:
            raise ValueError("participant cannot block themselves")
        return self


class SafetyReport(ContractModel):
    """A private, idempotent report retained for controlled moderation review."""

    report_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    reporter_id: str = Field(min_length=1)
    target_participant_id: str = Field(min_length=1)
    category: Literal["harassment", "privacy", "spam", "other"]
    description: str = Field(min_length=1, max_length=500)
    state_version: int = Field(ge=0)
    status: Literal["open", "acknowledged", "resolved"] = "open"

    @model_validator(mode="after")
    def reporter_and_target_must_differ(self) -> "SafetyReport":
        if self.reporter_id == self.target_participant_id:
            raise ValueError("reporter cannot report themselves")
        return self


class SafetyReportStatusAudit(ContractModel):
    """Immutable trusted record for one real moderator report transition."""

    event_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    moderator_id: str = Field(min_length=1)
    from_status: Literal["open", "acknowledged", "resolved"]
    to_status: Literal["open", "acknowledged", "resolved"]
    reason: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def status_must_advance(self) -> "SafetyReportStatusAudit":
        allowed = {
            "open": {"acknowledged", "resolved"},
            "acknowledged": {"resolved"},
            "resolved": set(),
        }
        if self.to_status not in allowed[self.from_status]:
            raise ValueError("safety report audit must record a forward transition")
        return self


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


class FollowUpOutcome(ContractModel):
    """A participant-reported result for one close-card follow-up item."""

    table_id: str = Field(min_length=1)
    follow_up_index: int = Field(ge=0)
    participant_id: str = Field(min_length=1)
    status: Literal["completed", "in_progress", "blocked", "dismissed"]
    note: str | None = Field(default=None, min_length=1, max_length=240)


class ValueFeedback(ContractModel):
    """One participant's post-close four-dimension value reflection."""

    table_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    cognitive_value: int = Field(ge=1, le=5)
    relationship_value: int = Field(ge=1, le=5)
    action_value: int = Field(ge=1, le=5)
    emotional_value: int = Field(ge=1, le=5)
    note: str | None = Field(default=None, min_length=1, max_length=240)
    would_join_again: bool


class FeedbackSummary(ContractModel):
    """Member-only aggregate of post-close value feedback."""

    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    eligible_participant_count: int = Field(ge=0)
    response_count: int = Field(ge=0)
    cognitive_average: float | None = Field(default=None, ge=1, le=5)
    relationship_average: float | None = Field(default=None, ge=1, le=5)
    action_average: float | None = Field(default=None, ge=1, le=5)
    emotional_average: float | None = Field(default=None, ge=1, le=5)
    would_join_again_count: int = Field(ge=0)


class TableEvaluation(ContractModel):
    """Member-scoped, read-only metrics for one table's conversation loop."""

    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    phase: Phase
    closed: bool
    participant_count: int = Field(ge=0, le=5)
    invitation_count: int = Field(ge=0)
    invitation_pending_count: int = Field(ge=0)
    invitation_accepted_count: int = Field(ge=0)
    invitation_declined_count: int = Field(ge=0)
    invitation_acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    peripheral_comment_count: int = Field(ge=0)
    promoted_comment_count: int = Field(ge=0)
    human_turn_count: int = Field(ge=0)
    intervention_count: int = Field(ge=0)
    reflected_intervention_count: int = Field(ge=0)
    effective_intervention_count: int = Field(ge=0)
    follow_up_count: int = Field(ge=0)
    follow_up_reported_count: int = Field(ge=0)
    follow_up_completed_count: int = Field(ge=0)
    follow_up_completion_rate: float | None = Field(default=None, ge=0, le=1)
    feedback_completion_rate: float = Field(ge=0, le=1)
    would_join_again_rate: float | None = Field(default=None, ge=0, le=1)
    feedback_summary: FeedbackSummary | None = None

    @model_validator(mode="after")
    def counts_are_consistent(self) -> "TableEvaluation":
        if self.reflected_intervention_count > self.intervention_count:
            raise ValueError("reflected interventions cannot exceed interventions")
        if self.effective_intervention_count > self.reflected_intervention_count:
            raise ValueError("effective interventions cannot exceed reflections")
        invitation_status_total = (
            self.invitation_pending_count
            + self.invitation_accepted_count
            + self.invitation_declined_count
        )
        if invitation_status_total > self.invitation_count:
            raise ValueError("invitation status counts cannot exceed invitations")
        if self.invitation_count and self.invitation_acceptance_rate is None:
            raise ValueError("invitations require an acceptance rate")
        if not self.invitation_count and self.invitation_acceptance_rate is not None:
            raise ValueError("empty invitation funnel must not have an acceptance rate")
        if self.promoted_comment_count > self.peripheral_comment_count:
            raise ValueError("promoted comments cannot exceed peripheral comments")
        if self.follow_up_reported_count > self.follow_up_count:
            raise ValueError("reported follow-ups cannot exceed follow-up items")
        if self.follow_up_completed_count > self.follow_up_reported_count:
            raise ValueError("completed follow-ups cannot exceed reported outcomes")
        if self.feedback_summary is not None:
            if self.feedback_summary.response_count > self.feedback_summary.eligible_participant_count:
                raise ValueError("feedback responses cannot exceed eligible participants")
            if self.feedback_summary.response_count and self.would_join_again_rate is None:
                raise ValueError("feedback responses require a would_join_again_rate")
        return self


class QuestionFootprintNextTable(ContractModel):
    """Public metadata for one direct child table in the question lineage."""

    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    core_question: str = Field(min_length=1, max_length=120)
    phase: Phase
    closed: bool = False


class QuestionFootprintEntry(ContractModel):
    """One member's evidence-backed contribution to a closed table."""

    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    core_question: str = Field(min_length=1, max_length=120)
    your_contribution: list[EvidenceStatement] = Field(default_factory=list, max_length=5)
    what_changed: list[EvidenceStatement] = Field(default_factory=list, max_length=8)
    next_tables: list[QuestionFootprintNextTable] = Field(default_factory=list, max_length=3)


class ActionEchoEntry(ContractModel):
    """One self-scoped follow-up that can be revisited after a table closes."""

    table_id: str = Field(min_length=1)
    state_version: int = Field(ge=0)
    core_question: str = Field(min_length=1, max_length=120)
    follow_up_index: int = Field(ge=0)
    item_type: Literal["suggestion", "commitment"]
    text: str = Field(min_length=1)
    evidence_turns: TurnEvidence
    status: Literal["completed", "in_progress", "blocked", "dismissed"] | None = None
    note: str | None = Field(default=None, min_length=1, max_length=240)


class PeripheralComment(ContractModel):
    """A public comment that never enters the core conversation turn stream."""

    comment_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    author_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=500)
    state_version: int = Field(ge=0)


class CommentPromotion(ContractModel):
    """Audit link for one explicit, safety-checked comment promotion."""

    promotion_id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    comment_id: str = Field(min_length=1)
    promoter_id: str = Field(min_length=1)
    turn_id: PositiveInt
    state_version: int = Field(ge=0)
    message_id: str = Field(min_length=1)


BehaviorEventType = Literal[
    "table_selected",
    "human_message",
    "relationship_saved",
    "follow_up_outcome",
    "table_closed",
    "value_feedback_submitted",
]


class BehaviorEvent(ContractModel):
    """Bounded, self-scoped product behavior signal; never a message archive."""

    event_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    event_type: BehaviorEventType
    table_id: str = Field(min_length=1)
    state_version: int | None = Field(default=None, ge=0, exclude_if=lambda value: value is None)
    related_participant_id: str | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)
    detail: str | None = Field(default=None, min_length=1, max_length=240, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def event_context_is_bounded(self) -> "BehaviorEvent":
        if self.event_type in {"human_message", "follow_up_outcome", "table_closed", "value_feedback_submitted"} and self.state_version is None:
            raise ValueError("state_version is required for table behavior events")
        if self.event_type == "relationship_saved" and self.related_participant_id is None:
            raise ValueError("relationship_saved requires related_participant_id")
        if self.related_participant_id == self.participant_id:
            raise ValueError("related_participant_id must differ from participant_id")
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
