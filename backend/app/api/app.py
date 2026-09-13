"""Minimal REST API for one explainable conversation table."""

import asyncio
import os
from collections.abc import Callable, Sequence
from itertools import islice
import time
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.domain import ActionEchoEntry, ActiveIntentPreview, ActiveIntentRequest, ActiveIntentSessionView, ActiveIntentSourcePreviewRequest, ActiveIntentTurnRequest, AgentActionEvent, AgentRunRecord, BehaviorEvent, BehaviorEventType, CommentPromotion, CommentPromotionCandidates, ContentSignal, FeedbackSummary, FollowUpItem, FollowUpOutcome, GateDecision, GroundingCard, HumanTurn, Invitation, InvitationPreference, InvitationStatus, InvitationView, InterventionRecord, JoinRequest, JoinRequestView, LobbyFitPreview, LobbyPreview, MatchPlan, MatchRequest, NoMatchPreference, OpportunityPreview, OpportunityRequest, ParticipantSavedTables, ParticipantSeed, ParticipantTableRecommendations, PeripheralComment, PersonalCard, PersonalContextConsent, PersonalContextPreview, PersonalContextScope, PersonalContextSignal, Phase, QuestionFootprintEntry, RelationshipMemory, RouteDecision, SafetyLevel, SafetyReport, SafetyReportStatusAudit, SafetyResolution, SavedTableItem, SharedBaseline, StageSummary, StageSummaryFeedback, StageSummaryTrigger, SyncUpgradeDecision, SyncUpgradeSignals, TableCandidatePreview, TableEvaluation, TableRecruitmentDecision, TableState, ValueFeedback
from app.matching import build_match_plan, evaluate_recruitment_need, infer_role_gaps, recommend_candidates
from app.opportunities import build_opportunity_preview
from app.orchestrator import build_personal_card, build_shared_baseline, enforce_safety, escalate_boundary_safety, evaluate_safety, evaluate_sync_upgrade
from app.orchestrator.run_service import TableRunService
from app.orchestrator.lease import SQLiteAgentRunLeaseStore
from app.providers import LLMProvider
from app.domain.schemas import EvidenceStatement
from app.demo.service import DemoTiming, JudgeDemoService
from app.demo.routes import register_demo_routes

from .repository import MAX_ACTION_ECHO_ITEMS, MAX_QUESTION_FOOTPRINT_ITEMS, MAX_SAVED_TABLES_PER_PARTICIPANT, MAX_TABLE_LINEAGE_DEPTH, MAX_TABLE_PARTICIPANTS, InMemoryTableRepository
from .privacy import project_state_for_viewer
from .websocket import DEFAULT_MAX_WEBSOCKET_EVENTS_PER_MINUTE, DEFAULT_MAX_WEBSOCKET_FRAME_BYTES, register_websocket_routes
from .rate_limit import DEFAULT_MAX_MUTATIONS_PER_MINUTE, MutationRateLimiter, SQLiteMutationRateLimiter
from .event_bus import EventBus
from .nudge import NudgeCooldown, NudgeResult, NudgeUnavailable, run_nudge
from .identity import ModeratorResolver, IdentityResolver, require_moderator_identity, require_request_identity
from .intent_sessions import ActiveIntentSessionStore, IntentSessionCapacityExhausted, IntentSessionTurnLimitReached, IntentSessionUnavailable, SQLiteActiveIntentSessionStore
from .match_tickets import (
    CandidateInvitationTicketStore,
    SQLiteCandidateInvitationTicketStore,
    SQLiteSourceMatchTicketStore,
    SourceMatchTicketStore,
)
from app.sources import CandidateSource, CandidateSourceError, ContentSignalSource, ContentSignalSourceError, PersonalContextSource, PersonalContextSourceError
from app.personal import build_personal_context_preview
from app.intake import build_active_intent_preview, build_active_intent_session_preview
from app.lobby import build_lobby_discovery, build_lobby_fit_preview, build_lobby_preview
from app.recommendations import MAX_PERSONALIZED_TABLES, build_personalized_table_recommendations
from app.comment_curation import MAX_COMMENT_PROMOTION_CANDIDATES, build_comment_promotion_candidates
from app.auth.zhihu import ZhihuOAuthService, register_zhihu_auth_routes


def _bounded_source_rows(rows: object, limit: int) -> list[object]:
    """Consume at most ``limit`` rows from an injected source iterable."""
    return list(islice(rows, limit))


class CreateTableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str | None = Field(default=None, min_length=1)
    core_question: str = Field(min_length=1)
    participants: list[ParticipantSeed] = Field(default_factory=list)
    origin_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )
    origin_signals: list[ContentSignal] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )

    @model_validator(mode="after")
    def origin_signal_ids_are_public_candidate_ids(self) -> "CreateTableRequest":
        snapshot_ids = [signal.signal_id for signal in self.origin_signals]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("origin_signals signal_id values must be unique")
        if self.origin_signals and not self.origin_signal_ids:
            self.origin_signal_ids = snapshot_ids
        if len(self.origin_signal_ids) != len(set(self.origin_signal_ids)):
            raise ValueError("origin_signal_ids must be unique")
        available = {
            signal_id
            for participant in self.participants
            for signal_id in participant.public_signal_ids
        }
        if any(signal_id not in available for signal_id in self.origin_signal_ids):
            raise ValueError("origin_signal_ids must reference participant public_signal_ids")
        if any(signal_id not in set(self.origin_signal_ids) for signal_id in snapshot_ids):
            raise ValueError("origin_signals must reference origin_signal_ids")
        return self


class ReplayResponse(BaseModel):
    """A replay keeps the original messages beside explainable state snapshots."""

    model_config = ConfigDict(extra="forbid")

    table_id: str
    messages: list[HumanTurn]
    snapshots: list[TableState]
    interventions: list[InterventionRecord] = Field(default_factory=list)
    comments: list[PeripheralComment] = Field(default_factory=list)
    comment_promotions: list[CommentPromotion] = Field(default_factory=list)
    source_signals: list[ContentSignal] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )
    stage_summaries: list[StageSummary] = Field(default_factory=list)
    summary_feedback: list[StageSummaryFeedback] = Field(default_factory=list)


class StageSummaryRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str
    accepted: bool
    state_version: int


class StageSummaryFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["misrepresented", "missing_point", "not_consensus", "ready_to_advance"]
    note: str | None = Field(default=None, min_length=1, max_length=240)
    evidence_turns: list[int] = Field(default_factory=list, max_length=10)


class CapabilitiesResponse(BaseModel):
    """Public runtime capabilities without deployment secrets."""

    model_config = ConfigDict(extra="forbid")

    repository: str = Field(min_length=1)
    conversation_provider: Literal["deterministic", "custom"]
    candidate_source_configured: bool
    content_source_configured: bool
    personal_context_source_configured: bool
    oauth_configured: bool = False
    websocket_available: bool = True
    max_table_participants: int = Field(ge=1, le=5)
    judge_demo_available: bool = False


class TableLineageItem(BaseModel):
    """Public, privacy-safe summary of one table in a question lineage."""

    model_config = ConfigDict(extra="forbid")

    table_id: str = Field(min_length=1)
    origin_table_id: str | None = Field(default=None, min_length=1)
    version: int = Field(ge=0)
    core_question: str = Field(min_length=1)
    origin_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )
    source_signals: list[ContentSignal] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )


class TableLineageResponse(BaseModel):
    """Oldest-to-current public question evolution chain."""

    model_config = ConfigDict(extra="forbid")

    table_id: str = Field(min_length=1)
    items: list[TableLineageItem] = Field(
        min_length=1,
        max_length=MAX_TABLE_LINEAGE_DEPTH,
    )


class ParticipantConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_shared: bool


class ParticipantInvitationPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference: InvitationPreference


class AccountInvitationPreferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str = Field(min_length=1)
    preference: InvitationPreference


class CreateInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: ParticipantSeed
    reason: str = Field(min_length=1, max_length=240)


class PreviewInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_token: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, min_length=1, max_length=240)


class JoinRequestCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    candidate: ParticipantSeed
    message: str | None = Field(default=None, min_length=1, max_length=240)


class JoinRequestApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=240)


class JoinRequestApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: JoinRequestView
    invitation: InvitationView


class RespondInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: bool


class InvitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation: InvitationView
    state: TableState | None = None


class InvitationInboxItem(BaseModel):
    """Candidate-only invitation summary with public table context."""

    model_config = ConfigDict(extra="forbid")

    invitation: InvitationView
    table: LobbyPreview
    can_respond: bool
    unavailable_reason: Literal[
        "invitation_processed",
        "table_closed",
        "table_soft_expired",
        "table_full",
        "candidate_already_joined",
        "matching_disabled",
    ] | None = None


class InvitationInboxResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str = Field(min_length=1)
    items: list[InvitationInboxItem] = Field(default_factory=list, max_length=100)
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class SyncUpgradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: SyncUpgradeDecision
    state: TableState


class NudgeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: GateDecision
    route: RouteDecision
    action: AgentActionEvent
    state: TableState


class MatchPreviewRequest(BaseModel):
    """Raw match input; durable account preferences are applied before matching."""

    model_config = ConfigDict(extra="forbid")

    core_question: str = Field(min_length=1)
    candidates: list[ParticipantSeed] = Field(min_length=2, max_length=20)
    table_size: int = Field(default=4, ge=2, le=5)

    @model_validator(mode="after")
    def candidate_ids_are_unique_and_fit(self) -> "MatchPreviewRequest":
        ids = [candidate.participant_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate participant_id values must be unique")
        if self.table_size > len(self.candidates):
            raise ValueError("table_size cannot exceed candidates")
        return self


class ConfirmMatchRequest(MatchPreviewRequest):
    table_id: str | None = Field(default=None, min_length=1)
    origin_signal_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )
    origin_signals: list[ContentSignal] = Field(
        default_factory=list,
        max_length=20,
        exclude_if=lambda value: not value,
    )

    @model_validator(mode="after")
    def origin_signal_ids_are_candidate_ids(self) -> "ConfirmMatchRequest":
        snapshot_ids = [signal.signal_id for signal in self.origin_signals]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("origin_signals signal_id values must be unique")
        if self.origin_signals and not self.origin_signal_ids:
            self.origin_signal_ids = snapshot_ids
        if len(self.origin_signal_ids) != len(set(self.origin_signal_ids)):
            raise ValueError("origin_signal_ids must be unique")
        available = {
            signal_id
            for candidate in self.candidates
            for signal_id in candidate.public_signal_ids
        }
        if any(signal_id not in available for signal_id in self.origin_signal_ids):
            raise ValueError("origin_signal_ids must reference candidate public_signal_ids")
        if any(signal_id not in set(self.origin_signal_ids) for signal_id in snapshot_ids):
            raise ValueError("origin_signals must reference origin_signal_ids")
        return self


class SourceMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_question: str = Field(min_length=1)
    query: str | None = Field(default=None, min_length=1)
    table_size: int = Field(default=4, ge=2, le=5)
    limit: int = Field(default=20, ge=2, le=20)


class SourceMatchConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_token: str = Field(min_length=1, max_length=200)
    table_id: str | None = Field(default=None, min_length=1)


class CandidatePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, min_length=1, max_length=120)
    limit: int = Field(default=10, ge=1, le=20)


class OpportunitySourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=20, ge=2, le=20)


class GroundingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, min_length=1, max_length=120)
    limit: int = Field(default=5, ge=1, le=20)


class PersonalContextSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=20, ge=1, le=20)
    scopes: list[PersonalContextScope] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def scopes_are_unique(self) -> "PersonalContextSourceRequest":
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError("personal context scopes must be unique")
        return self


class PersonalContextConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scopes: list[PersonalContextScope] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def scopes_are_unique(self) -> "PersonalContextConsentRequest":
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError("personal context scopes must be unique")
        return self


class BehaviorEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: BehaviorEventType
    table_id: str = Field(min_length=1)
    state_version: int | None = Field(default=None, ge=0)
    related_participant_id: str | None = Field(default=None, min_length=1)
    detail: str | None = Field(default=None, min_length=1, max_length=240)


_SERVER_GENERATED_BEHAVIOR_EVENTS = frozenset({
    "table_closed",
    "value_feedback_submitted",
})


class MatchedTableResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: MatchPlan
    state: TableState


class CloseArtifactsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str
    state_version: int
    shared_baseline: SharedBaseline
    personal_card: PersonalCard


class FollowUpOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "in_progress", "blocked", "dismissed"]
    note: str | None = Field(default=None, min_length=1, max_length=240)


class ValueFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cognitive_value: int = Field(ge=1, le=5)
    relationship_value: int = Field(ge=1, le=5)
    action_value: int = Field(ge=1, le=5)
    emotional_value: int = Field(ge=1, le=5)
    note: str | None = Field(default=None, min_length=1, max_length=240)
    would_join_again: bool


class PeripheralCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=500)


class CommentPromotionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: PeripheralComment
    promotion: CommentPromotion
    turn: HumanTurn
    state: TableState


class SafetyReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    target_participant_id: str = Field(min_length=1)
    category: Literal["harassment", "privacy", "spam", "other"]
    description: str = Field(min_length=1, max_length=500)


class SafetyReportStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["acknowledged", "resolved"]
    reason: str | None = Field(default=None, min_length=1, max_length=240)


class SafetyResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["resume", "remove_participant"]
    participant_id: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1, max_length=240)


class SafetyResolutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: SafetyResolution
    state: TableState


class RecomposeTableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str | None = Field(default=None, min_length=1)
    participants: list[ParticipantSeed] = Field(min_length=2, max_length=5)


class RecomposeTableResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_table_id: str
    source_state_version: int = Field(ge=0)
    new_table_id: str
    evolved_question: EvidenceStatement
    state: TableState


class SoftExpireRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=240)


class FollowUpStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    follow_up_index: int = Field(ge=0)
    item: FollowUpItem
    outcome: FollowUpOutcome | None = None


def create_app(
    repository: InMemoryTableRepository | None = None,
    provider: LLMProvider | None = None,
    candidate_source: CandidateSource | None = None,
    candidate_source_timeout_seconds: float = 5.0,
    content_source: ContentSignalSource | None = None,
    content_source_timeout_seconds: float = 5.0,
    personal_context_source: PersonalContextSource | None = None,
    personal_context_source_timeout_seconds: float = 5.0,
    identity_resolver: IdentityResolver | None = None,
    oauth_service: ZhihuOAuthService | None = None,
    moderator_resolver: ModeratorResolver | None = None,
    websocket_allowed_origins: Sequence[str] | None = None,
    websocket_max_frame_bytes: int | None = None,
    websocket_max_events_per_minute: int | None = None,
    rest_max_mutations_per_minute: int | None = None,
    source_match_preview_ttl_seconds: float = 300.0,
    intent_session_ttl_seconds: float = 900.0,
    sync_window_seconds: float = 1800.0,
    event_bus: EventBus | None = None,
    shared_rate_limit_path: str | os.PathLike[str] | None = None,
    shared_ephemeral_store_path: str | os.PathLike[str] | None = None,
    clock: Callable[[], float] = time.time,
    enable_judge_demo: bool = False,
    judge_demo_timing: DemoTiming | None = None,
    stage_summary_timeout_seconds: float = 8.0,
) -> FastAPI:
    """Create an app with an injectable repository for tests and future persistence."""
    if candidate_source_timeout_seconds <= 0:
        raise ValueError("candidate_source_timeout_seconds must be positive")
    if content_source_timeout_seconds <= 0:
        raise ValueError("content_source_timeout_seconds must be positive")
    if personal_context_source_timeout_seconds <= 0:
        raise ValueError("personal_context_source_timeout_seconds must be positive")
    if source_match_preview_ttl_seconds <= 0:
        raise ValueError("source_match_preview_ttl_seconds must be positive")
    if intent_session_ttl_seconds <= 0:
        raise ValueError("intent_session_ttl_seconds must be positive")
    if sync_window_seconds <= 0:
        raise ValueError("sync_window_seconds must be positive")
    raw_websocket_origins = (
        os.getenv("WS_ALLOWED_ORIGINS", "")
        if websocket_allowed_origins is None
        else ",".join(websocket_allowed_origins)
    )
    allowed_websocket_origins = tuple(
        origin.strip() for origin in raw_websocket_origins.split(",") if origin.strip()
    )
    if any(origin == "*" or "*" in origin for origin in allowed_websocket_origins):
        raise ValueError("websocket_allowed_origins must not contain wildcards")
    raw_frame_bytes = (
        os.getenv("WS_MAX_FRAME_BYTES", str(DEFAULT_MAX_WEBSOCKET_FRAME_BYTES))
        if websocket_max_frame_bytes is None
        else str(websocket_max_frame_bytes)
    )
    try:
        max_websocket_frame_bytes = int(raw_frame_bytes)
    except ValueError as error:
        raise ValueError("websocket_max_frame_bytes must be a positive integer") from error
    if max_websocket_frame_bytes <= 0:
        raise ValueError("websocket_max_frame_bytes must be a positive integer")
    raw_event_limit = (
        os.getenv(
            "WS_MAX_EVENTS_PER_MINUTE",
            str(DEFAULT_MAX_WEBSOCKET_EVENTS_PER_MINUTE),
        )
        if websocket_max_events_per_minute is None
        else str(websocket_max_events_per_minute)
    )
    try:
        max_websocket_events_per_minute = int(raw_event_limit)
    except ValueError as error:
        raise ValueError("websocket_max_events_per_minute must be a positive integer") from error
    if max_websocket_events_per_minute <= 0:
        raise ValueError("websocket_max_events_per_minute must be a positive integer")
    raw_rest_limit = (
        os.getenv(
            "REST_MAX_MUTATIONS_PER_MINUTE",
            str(DEFAULT_MAX_MUTATIONS_PER_MINUTE),
        )
        if rest_max_mutations_per_minute is None
        else str(rest_max_mutations_per_minute)
    )
    try:
        max_rest_mutations_per_minute = int(raw_rest_limit)
    except ValueError as error:
        raise ValueError("rest_max_mutations_per_minute must be a positive integer") from error
    if max_rest_mutations_per_minute <= 0:
        raise ValueError("rest_max_mutations_per_minute must be a positive integer")
    repo = repository or InMemoryTableRepository()
    effective_identity_resolver = identity_resolver or (
        oauth_service.identity_resolver if oauth_service is not None else None
    )
    configured_ephemeral_path = (
        os.getenv("SHARED_EPHEMERAL_STORE_PATH", "").strip()
        if shared_ephemeral_store_path is None
        else os.fspath(shared_ephemeral_store_path)
    )
    if configured_ephemeral_path:
        source_match_tickets = SQLiteSourceMatchTicketStore(
            configured_ephemeral_path,
            ttl_seconds=source_match_preview_ttl_seconds,
            clock=time.time,
        )
        candidate_invitation_tickets = SQLiteCandidateInvitationTicketStore(
            configured_ephemeral_path,
            ttl_seconds=source_match_preview_ttl_seconds,
            clock=time.time,
        )
        intent_sessions = SQLiteActiveIntentSessionStore(
            configured_ephemeral_path,
            ttl_seconds=intent_session_ttl_seconds,
            clock=time.time,
        )
    else:
        source_match_tickets = SourceMatchTicketStore(ttl_seconds=source_match_preview_ttl_seconds)
        candidate_invitation_tickets = CandidateInvitationTicketStore(
            ttl_seconds=source_match_preview_ttl_seconds,
        )
        intent_sessions = ActiveIntentSessionStore(
            ttl_seconds=intent_session_ttl_seconds,
            clock=clock,
        )
    api = FastAPI(title="组一桌 Conversation Orchestrator")
    api.state.repository = repo
    api.state.provider = provider
    api.state.candidate_source = candidate_source
    api.state.content_source = content_source
    api.state.personal_context_source = personal_context_source
    api.state.source_match_tickets = source_match_tickets
    api.state.candidate_invitation_tickets = candidate_invitation_tickets
    api.state.intent_sessions = intent_sessions
    api.state.identity_resolver = effective_identity_resolver
    api.state.oauth_service = oauth_service
    api.state.moderator_resolver = moderator_resolver
    api.state.sync_window_seconds = sync_window_seconds
    configured_rate_limit_path = (
        os.getenv("SHARED_RATE_LIMIT_PATH", "").strip()
        if shared_rate_limit_path is None
        else os.fspath(shared_rate_limit_path)
    )
    rest_rate_limiter = (
        SQLiteMutationRateLimiter(
            configured_rate_limit_path,
            max_rest_mutations_per_minute,
        )
        if configured_rate_limit_path
        else MutationRateLimiter(max_rest_mutations_per_minute)
    )
    raw_origins = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=effective_identity_resolver is not None,
        allow_methods=["DELETE", "GET", "PATCH", "POST", "PUT", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type"],
    )

    @api.middleware("http")
    async def limit_rest_mutations(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            parts = request.url.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "tables":
                try:
                    demo_state = repo.get(parts[1])
                except KeyError:
                    demo_state = None
                if demo_state is not None and demo_state.demo is not None:
                    actor = next((request.query_params.get(key) for key in ("participant_id", "viewer_id", "inviter_id", "author_id") if request.query_params.get(key)), None)
                    if actor != demo_state.demo.owner_participant_id:
                        return JSONResponse(status_code=403, content={"detail": "只有本次体验的参与者可以操作；模拟桌友由后端管理"})
                    try:
                        require_request_identity(effective_identity_resolver, request, actor)
                    except HTTPException as error:
                        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
            client = request.client
            client_key = client.host if client is not None and client.host else "unknown"
            allowed, retry_after = rest_rate_limiter.allow(client_key)
            if not allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "too many REST mutations; retry later"},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)

    register_websocket_routes(
        api,
        repo,
        provider,
        effective_identity_resolver,
        allowed_websocket_origins or None,
        max_websocket_frame_bytes,
        max_websocket_events_per_minute,
        clock,
        event_bus,
    )
    api.state.table_run_service = TableRunService(
        repo,
        provider=provider,
        broadcast=api.state.table_broadcast,
        broadcast_state=api.state.table_broadcast_state,
        lease_store=(
            SQLiteAgentRunLeaseStore(configured_ephemeral_path, ttl_seconds=max(45.0, stage_summary_timeout_seconds + 10.0))
            if configured_ephemeral_path else None
        ),
        clock=clock,
        deadline_seconds=stage_summary_timeout_seconds,
    )
    api.state.judge_demo_service = JudgeDemoService(
        repo, provider, enabled=enable_judge_demo,
        commit=api.state.table_commit_message, broadcast=api.state.table_broadcast,
        timing=judge_demo_timing,
    )
    register_demo_routes(api, api.state.judge_demo_service, effective_identity_resolver)
    if oauth_service is not None:
        register_zhihu_auth_routes(api, oauth_service)

    @api.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/capabilities", response_model=CapabilitiesResponse)
    def capabilities() -> CapabilitiesResponse:
        """Describe configured product paths without exposing secrets or identities."""
        return CapabilitiesResponse(
            repository=type(repo).__name__,
            conversation_provider="deterministic" if provider is None else "custom",
            candidate_source_configured=candidate_source is not None,
            content_source_configured=content_source is not None,
            personal_context_source_configured=personal_context_source is not None,
            oauth_configured=oauth_service is not None,
            websocket_available=True,
            max_table_participants=MAX_TABLE_PARTICIPANTS,
            judge_demo_available=api.state.judge_demo_service.available,
        )

    @api.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready", "repository": type(repo).__name__}

    def table_or_404(table_id: str) -> TableState:
        try:
            state, _expired = repo.expire_sync_if_due(table_id, now=clock())
            return state
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    def refresh_sync_windows() -> None:
        for state in repo.list_tables(include_closed=True):
            repo.expire_sync_if_due(state.table_id, now=clock())

    def projected(state: TableState, participant_id: str | None = None) -> TableState:
        if participant_id is not None and participant_id not in state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {participant_id}")
        return project_state_for_viewer(state, participant_id)

    def effective_candidates(
        candidates: Sequence[ParticipantSeed],
    ) -> list[ParticipantSeed]:
        """Overlay durable account preferences on request/source snapshots."""
        return [repo.apply_account_invitation_preference(item) for item in candidates]

    def effective_match_request(payload: MatchPreviewRequest) -> MatchRequest:
        """Revalidate match capacity after applying durable hard opt-outs."""
        try:
            return MatchRequest(
                core_question=payload.core_question,
                candidates=effective_candidates(payload.candidates),
                table_size=payload.table_size,
            )
        except ValidationError as error:
            raise HTTPException(
                status_code=409,
                detail="not enough invitation-eligible candidates for this table",
            ) from error

    async def broadcast_table_event(table_id: str, event: dict) -> None:
        """Fan out a public event when the WebSocket adapter is installed."""
        broadcaster = getattr(api.state, "table_broadcast", None)
        if broadcaster is not None:
            await broadcaster(table_id, event)

    async def broadcast_table_state(table_id: str, state: TableState) -> None:
        """Fan out the privacy-projected state after a REST mutation."""
        broadcaster = getattr(api.state, "table_broadcast_state", None)
        if broadcaster is not None:
            await broadcaster(table_id, state)

    @api.post("/tables", response_model=TableState, status_code=status.HTTP_201_CREATED)
    def create_table(payload: CreateTableRequest) -> TableState:
        table_id = payload.table_id or uuid4().hex
        try:
            return projected(
                repo.create(
                    table_id,
                    payload.core_question,
                    payload.participants,
                    origin_signal_ids=payload.origin_signal_ids,
                    origin_signals=payload.origin_signals,
                )
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @api.get("/tables", response_model=list[TableState])
    def list_tables(
        request: Request,
        participant_id: str | None = Query(default=None),
        include_closed: bool = Query(default=False),
    ) -> list[TableState]:
        if participant_id is not None:
            require_request_identity(identity_resolver, request, participant_id)
        refresh_sync_windows()
        return [
            project_state_for_viewer(state, participant_id)
            for state in repo.list_tables(include_closed=include_closed)
            if state.demo is None or state.demo.owner_participant_id == participant_id
        ]

    @api.get("/tables/discovery", response_model=list[LobbyPreview])
    def discover_lobbies(
        limit: int = Query(default=20, ge=1, le=20),
    ) -> list[LobbyPreview]:
        """Return bounded public Lobby cards for homepage table discovery."""
        refresh_sync_windows()
        return build_lobby_discovery([state for state in repo.list_tables() if state.demo is None], limit=limit)

    @api.get("/tables/{table_id}/lobby", response_model=LobbyPreview)
    def get_lobby_preview(table_id: str) -> LobbyPreview:
        """Return the public pre-entry questions without exposing table internals."""
        return build_lobby_preview(table_or_404(table_id))

    @api.post("/tables/{table_id}/lobby-fit", response_model=LobbyFitPreview)
    def preview_lobby_fit(
        table_id: str,
        payload: ParticipantSeed,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> LobbyFitPreview:
        """Explain a possible seat without persisting the candidate or changing the table."""
        require_request_identity(identity_resolver, request, participant_id)
        if payload.participant_id != participant_id:
            raise HTTPException(status_code=403, detail="candidate does not match participant_id")
        state = table_or_404(table_id)
        blocked = any(
            repo.is_no_match(member_id, participant_id)
            for member_id in state.participants
        )
        return build_lobby_fit_preview(state, payload, blocked=blocked)

    @api.get("/participants/{participant_id}/relationship-memory", response_model=list[RelationshipMemory])
    def get_relationship_memory(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> list[RelationshipMemory]:
        """Return evidence-backed old-table reminders only to the participant themselves."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        return repo.relationship_memories(participant_id)

    @api.get(
        "/participants/{participant_id}/invitation-preference",
        response_model=AccountInvitationPreferenceResponse,
    )
    def get_account_invitation_preference(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> AccountInvitationPreferenceResponse:
        """Return the caller's durable preference for future proactive invitations."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        preference = (
            repo.account_invitation_preference(participant_id)
            or InvitationPreference.FEW
        )
        return AccountInvitationPreferenceResponse(
            participant_id=participant_id,
            preference=preference,
        )

    @api.put(
        "/participants/{participant_id}/invitation-preference",
        response_model=AccountInvitationPreferenceResponse,
    )
    def set_account_invitation_preference(
        participant_id: str,
        payload: ParticipantInvitationPreferenceRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> AccountInvitationPreferenceResponse:
        """Save a self-scoped preference without rewriting existing table history."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            preference = repo.set_account_invitation_preference(
                participant_id,
                payload.preference,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return AccountInvitationPreferenceResponse(
            participant_id=participant_id,
            preference=preference,
        )

    @api.get(
        "/participants/{participant_id}/question-footprint",
        response_model=list[QuestionFootprintEntry],
    )
    def get_question_footprint(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
        limit: int = Query(default=20, ge=1, le=MAX_QUESTION_FOOTPRINT_ITEMS),
    ) -> list[QuestionFootprintEntry]:
        """Return the caller's bounded contribution history across closed tables."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        return repo.question_footprint(participant_id, limit=limit)

    @api.get(
        "/participants/{participant_id}/action-echoes",
        response_model=list[ActionEchoEntry],
    )
    def get_action_echoes(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
        limit: int = Query(default=20, ge=1, le=MAX_ACTION_ECHO_ITEMS),
    ) -> list[ActionEchoEntry]:
        """Return this member's bounded follow-up outcomes across closed tables."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        return repo.action_echoes(participant_id, limit=limit)

    @api.post(
        "/tables/{table_id}/relationships/{related_participant_id}/save",
        response_model=BehaviorEvent,
        status_code=status.HTTP_201_CREATED,
    )
    def save_relationship(
        table_id: str,
        related_participant_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> BehaviorEvent:
        """Record a member's explicit post-close relationship choice."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if state.demo is not None:
            raise HTTPException(status_code=409, detail="模拟桌友不能添加为真实好友")
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="relationship save requires a closed table")
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        if related_participant_id not in state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {related_participant_id}")
        if participant_id == related_participant_id:
            raise HTTPException(status_code=409, detail="participant cannot save a relationship with themselves")
        try:
            event, _created = repo.record_behavior_event(BehaviorEvent(
                event_id=f"{table_id}:relationship:{participant_id}:{related_participant_id}",
                participant_id=participant_id,
                event_type="relationship_saved",
                table_id=table_id,
                state_version=state.version,
                related_participant_id=related_participant_id,
                detail="saved",
            ))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return event

    @api.post(
        "/participants/{participant_id}/behavior-events",
        response_model=BehaviorEvent,
        status_code=status.HTTP_201_CREATED,
    )
    def record_behavior_event(
        participant_id: str,
        payload: BehaviorEventRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> BehaviorEvent:
        """Record a bounded product behavior signal for the participant themself."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        if payload.event_type in _SERVER_GENERATED_BEHAVIOR_EVENTS:
            raise HTTPException(
                status_code=409,
                detail="this behavior event is generated by its dedicated server path",
            )
        try:
            event, _created = repo.record_behavior_event(
                BehaviorEvent(participant_id=participant_id, **payload.model_dump())
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return event

    @api.post(
        "/tables/{table_id}/select",
        response_model=BehaviorEvent,
        status_code=status.HTTP_201_CREATED,
    )
    def select_table(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> BehaviorEvent:
        """Record an explicit open-table selection without mutating membership."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is closed")
        if state.conversation.soft_expired:
            raise HTTPException(status_code=409, detail="table is soft-expired")
        try:
            event, _created = repo.record_behavior_event(BehaviorEvent(
                event_id=f"{participant_id}:table-selected:{table_id}",
                participant_id=participant_id,
                event_type="table_selected",
                table_id=table_id,
                detail="selected",
            ))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return event

    @api.get(
        "/participants/{participant_id}/behavior-events",
        response_model=list[BehaviorEvent],
    )
    def get_behavior_events(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> list[BehaviorEvent]:
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            return repo.behavior_events(participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.put(
        "/participants/{participant_id}/saved-tables/{table_id}",
        response_model=SavedTableItem,
    )
    def save_table_for_later(
        participant_id: str,
        table_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> SavedTableItem:
        """Privately save one existing table without changing the table itself."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        refresh_sync_windows()
        state = table_or_404(table_id)
        try:
            repo.save_table(participant_id, table_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return SavedTableItem(table_id=table_id, lobby=build_lobby_preview(state))

    @api.delete(
        "/participants/{participant_id}/saved-tables/{table_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def remove_saved_table(
        participant_id: str,
        table_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> None:
        """Remove one private save without changing the underlying table."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        table_or_404(table_id)
        try:
            repo.unsave_table(participant_id, table_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return None

    @api.get(
        "/participants/{participant_id}/saved-tables",
        response_model=ParticipantSavedTables,
    )
    def get_saved_tables(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=MAX_SAVED_TABLES_PER_PARTICIPANT),
    ) -> ParticipantSavedTables:
        """Return the caller's private saved tables, newest save first."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        refresh_sync_windows()
        try:
            table_ids = repo.saved_table_ids(participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        page_ids = table_ids[offset:offset + limit]
        return ParticipantSavedTables(
            participant_id=participant_id,
            total=len(table_ids),
            offset=offset,
            limit=limit,
            items=[
                SavedTableItem(
                    table_id=table_id,
                    lobby=build_lobby_preview(repo.get(table_id)),
                )
                for table_id in page_ids
            ],
        )

    @api.get(
        "/participants/{participant_id}/table-recommendations",
        response_model=ParticipantTableRecommendations,
    )
    def get_personalized_table_recommendations(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
        limit: int = Query(default=5, ge=1, le=MAX_PERSONALIZED_TABLES),
    ) -> ParticipantTableRecommendations:
        """Rank eligible public tables from the caller's resettable behavior signals."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        refresh_sync_windows()
        history = {
            state.table_id: state
            for state in repo.list_tables(include_closed=True)
            if state.demo is None
        }
        candidates = [
            state
            for state in repo.list_tables()
            if state.demo is None and not any(
                repo.is_no_match(participant_id, member_id)
                for member_id in state.participants
            )
        ]
        return build_personalized_table_recommendations(
            participant_id,
            candidates,
            history,
            repo.behavior_events(participant_id),
            limit=limit,
        )

    @api.delete(
        "/participants/{participant_id}/behavior-events",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def clear_behavior_events(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> None:
        """Let a participant erase only their private behavior ledger."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            repo.clear_behavior_events(participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return None

    @api.put(
        "/participants/{participant_id}/personal-context/consent",
        response_model=PersonalContextConsent,
    )
    def grant_personal_context_consent(
        participant_id: str,
        payload: PersonalContextConsentRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> PersonalContextConsent:
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            return repo.set_personal_context_consent(
                PersonalContextConsent(viewer_id=participant_id, scopes=payload.scopes)
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.delete(
        "/participants/{participant_id}/personal-context/consent",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def revoke_personal_context_consent(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> None:
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            repo.revoke_personal_context_consent(participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.get(
        "/participants/{participant_id}/personal-context/consent",
        response_model=PersonalContextConsent,
    )
    def get_personal_context_consent(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> PersonalContextConsent:
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        consent = repo.personal_context_consent(participant_id)
        if consent is None:
            raise HTTPException(status_code=404, detail="personal context consent not found")
        return consent

    @api.post(
        "/participants/{participant_id}/no-match/{blocked_participant_id}",
        response_model=NoMatchPreference,
        status_code=status.HTTP_201_CREATED,
    )
    def set_no_match_preference(
        participant_id: str,
        blocked_participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> NoMatchPreference:
        """Let a participant opt out of future matching with one person."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            return repo.set_no_match(participant_id, blocked_participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.delete(
        "/participants/{participant_id}/no-match/{blocked_participant_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def remove_no_match_preference(
        participant_id: str,
        blocked_participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> None:
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            repo.remove_no_match(participant_id, blocked_participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.get(
        "/participants/{participant_id}/no-match",
        response_model=list[NoMatchPreference],
    )
    def get_no_match_preferences(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> list[NoMatchPreference]:
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            return repo.no_match_preferences(participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.post("/opportunities/preview", response_model=OpportunityPreview)
    def preview_opportunity(payload: OpportunityRequest) -> OpportunityPreview:
        return build_opportunity_preview(payload)

    @api.post("/intents/preview", response_model=ActiveIntentPreview)
    def preview_active_intent(payload: ActiveIntentRequest) -> ActiveIntentPreview:
        """Route an active demand toward clarification, an open table, or a new table."""
        return build_active_intent_preview(
            payload.message,
            [state for state in repo.list_tables() if state.demo is None],
            limit=payload.limit,
        )

    def active_intent_session_view(session) -> ActiveIntentSessionView:
        preview = build_active_intent_session_preview(
            session.messages,
            [state for state in repo.list_tables() if state.demo is None],
            limit=session.limit,
        )
        remaining_turns = session.max_turns - session.turn_count
        session_status = (
            "ready"
            if preview.route != "clarify"
            else "exhausted"
            if remaining_turns == 0
            else "clarifying"
        )
        return ActiveIntentSessionView(
            session_id=session.session_id,
            participant_id=session.participant_id,
            status=session_status,
            messages=list(session.messages),
            turn_count=session.turn_count,
            max_turns=session.max_turns,
            remaining_turns=remaining_turns,
            preview=preview,
        )

    def require_active_intent_owner(
        participant_id: str,
        request: Request,
        viewer_id: str,
    ) -> None:
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")

    @api.post(
        "/participants/{participant_id}/intent-sessions",
        response_model=ActiveIntentSessionView,
        status_code=status.HTTP_201_CREATED,
    )
    def create_active_intent_session(
        participant_id: str,
        payload: ActiveIntentRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> ActiveIntentSessionView:
        """Start a self-scoped, short-lived active-demand clarification session."""
        require_active_intent_owner(participant_id, request, viewer_id)
        try:
            session = intent_sessions.create(
                participant_id=participant_id,
                message=payload.message,
                limit=payload.limit,
            )
        except IntentSessionCapacityExhausted as error:
            raise HTTPException(
                status_code=503,
                detail="active intent session temporarily unavailable",
            ) from error
        return active_intent_session_view(session)

    @api.get(
        "/participants/{participant_id}/intent-sessions/{session_id}",
        response_model=ActiveIntentSessionView,
    )
    def get_active_intent_session(
        participant_id: str,
        session_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> ActiveIntentSessionView:
        """Read current short-term context and re-evaluate its public route."""
        require_active_intent_owner(participant_id, request, viewer_id)
        try:
            session = intent_sessions.get(session_id, participant_id)
        except IntentSessionUnavailable as error:
            raise HTTPException(status_code=404, detail="active intent session not found") from error
        return active_intent_session_view(session)

    @api.post(
        "/participants/{participant_id}/intent-sessions/{session_id}/turns",
        response_model=ActiveIntentSessionView,
    )
    def append_active_intent_turn(
        participant_id: str,
        session_id: str,
        payload: ActiveIntentTurnRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> ActiveIntentSessionView:
        """Append one clarification, or explicitly replace the current intent context."""
        require_active_intent_owner(participant_id, request, viewer_id)
        try:
            session = intent_sessions.append(
                session_id,
                participant_id,
                payload.message,
                replace_context=payload.replace_context,
            )
        except IntentSessionUnavailable as error:
            raise HTTPException(status_code=404, detail="active intent session not found") from error
        except IntentSessionTurnLimitReached as error:
            raise HTTPException(
                status_code=409,
                detail="active intent session turn limit reached",
            ) from error
        return active_intent_session_view(session)

    @api.post(
        "/participants/{participant_id}/intent-sessions/{session_id}/source-preview",
        response_model=MatchPlan,
    )
    async def preview_active_intent_source(
        participant_id: str,
        session_id: str,
        payload: ActiveIntentSourcePreviewRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> MatchPlan:
        """Search authorized candidates for a clarified new-table intent."""
        require_active_intent_owner(participant_id, request, viewer_id)
        try:
            session = intent_sessions.get(session_id, participant_id)
        except IntentSessionUnavailable as error:
            raise HTTPException(status_code=404, detail="active intent session not found") from error
        session_view = active_intent_session_view(session)
        if session_view.preview.route == "clarify":
            raise HTTPException(
                status_code=409,
                detail="active intent session still needs clarification",
            )
        if session_view.preview.route == "join_existing":
            raise HTTPException(
                status_code=409,
                detail="active intent session already has existing table candidates",
            )
        return await preview_source_match(SourceMatchRequest(
            core_question=session_view.preview.normalized_question,
            query=session_view.preview.normalized_question,
            table_size=payload.table_size,
            limit=payload.limit,
        ))

    @api.delete(
        "/participants/{participant_id}/intent-sessions/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_active_intent_session(
        participant_id: str,
        session_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> None:
        """Dismiss a short-term intent session and its in-memory context."""
        require_active_intent_owner(participant_id, request, viewer_id)
        try:
            intent_sessions.delete(session_id, participant_id)
        except IntentSessionUnavailable as error:
            raise HTTPException(status_code=404, detail="active intent session not found") from error

    @api.post("/opportunities/source-preview", response_model=OpportunityPreview)
    async def preview_source_opportunity(payload: OpportunitySourceRequest) -> OpportunityPreview:
        """Fetch authorized public signals, then run the deterministic opportunity detector."""
        if content_source is None:
            raise HTTPException(status_code=503, detail="content source is not configured")
        try:
            raw_signals = await asyncio.wait_for(
                content_source.search(query=payload.query, limit=payload.limit),
                timeout=content_source_timeout_seconds,
            )
            signals = [
                item if isinstance(item, ContentSignal) else ContentSignal.model_validate(item)
                for item in _bounded_source_rows(raw_signals, payload.limit)
            ]
            request = OpportunityRequest(query=payload.query, signals=signals)
        except ContentSignalSourceError as error:
            raise HTTPException(status_code=502, detail="content source unavailable") from error
        except TimeoutError as error:
            raise HTTPException(status_code=502, detail="content source timed out") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=502, detail="content source returned invalid signals") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="content source unavailable") from error
        return build_opportunity_preview(request)

    @api.post("/personal-context/source-preview", response_model=PersonalContextPreview)
    async def preview_personal_context(
        payload: PersonalContextSourceRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> PersonalContextPreview:
        """Preview viewer-owned context without persisting or broadcasting it."""
        require_request_identity(identity_resolver, request, viewer_id)
        consent = repo.personal_context_consent(viewer_id)
        if consent is None:
            raise HTTPException(status_code=403, detail="personal context consent required")
        if not set(payload.scopes).issubset(set(consent.scopes)):
            raise HTTPException(status_code=403, detail="personal context scope not granted")
        if personal_context_source is None:
            raise HTTPException(status_code=503, detail="personal context source is not configured")
        try:
            raw_signals = await asyncio.wait_for(
                personal_context_source.search(
                    viewer_id=viewer_id,
                    scopes=payload.scopes,
                    query=payload.query,
                    limit=payload.limit,
                ),
                timeout=personal_context_source_timeout_seconds,
            )
            signals = [
                item if isinstance(item, PersonalContextSignal)
                else PersonalContextSignal.model_validate(item)
                for item in _bounded_source_rows(raw_signals, payload.limit)
            ]
            return build_personal_context_preview(viewer_id, payload.query, signals)
        except PersonalContextSourceError as error:
            raise HTTPException(status_code=502, detail="personal context source unavailable") from error
        except TimeoutError as error:
            raise HTTPException(status_code=502, detail="personal context source timed out") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=502, detail="personal context source returned invalid signals") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="personal context source unavailable") from error

    @api.post("/tables/{table_id}/grounding", response_model=GroundingCard)
    async def stage_grounding_card(
        table_id: str,
        payload: GroundingRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> GroundingCard:
        """Fetch one public source excerpt for the next evidence-backed GROUND."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        if state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is closed")
        if state.conversation.soft_expired:
            raise HTTPException(status_code=409, detail="table is soft-expired")
        if content_source is None:
            raise HTTPException(status_code=503, detail="content source is not configured")
        try:
            raw_signals = await asyncio.wait_for(
                content_source.search(
                    query=payload.query or state.core_question,
                    limit=payload.limit,
                ),
                timeout=content_source_timeout_seconds,
            )
            signals = [
                item if isinstance(item, ContentSignal)
                else ContentSignal.model_validate(item)
                for item in _bounded_source_rows(raw_signals, payload.limit)
            ]
        except ContentSignalSourceError as error:
            raise HTTPException(status_code=502, detail="content source unavailable") from error
        except TimeoutError as error:
            raise HTTPException(status_code=502, detail="content source timed out") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=502, detail="content source returned invalid signals") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="content source unavailable") from error
        if not signals:
            raise HTTPException(status_code=404, detail="no grounding source signal found")
        signal = signals[0]
        card = GroundingCard(
            title=signal.title,
            excerpt=signal.excerpt,
            source_ref=signal.source_ref,
            signal_id=signal.signal_id,
        )
        try:
            repo.set_trusted_grounding_card(table_id, card)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return card

    @api.post("/matches/preview", response_model=MatchPlan)
    def preview_match(payload: MatchPreviewRequest) -> MatchPlan:
        return build_match_plan(effective_match_request(payload))

    @api.post("/matches/source-preview", response_model=MatchPlan)
    async def preview_source_match(payload: SourceMatchRequest) -> MatchPlan:
        """Run an injected, authorized source through the same match preview."""
        if candidate_source is None:
            raise HTTPException(status_code=503, detail="candidate source is not configured")
        try:
            raw_candidates = await asyncio.wait_for(
                candidate_source.search(
                    query=payload.query or payload.core_question,
                    limit=payload.limit,
                ),
                timeout=candidate_source_timeout_seconds,
            )
            candidates = [
                item if isinstance(item, ParticipantSeed) else ParticipantSeed.model_validate(item)
                for item in _bounded_source_rows(raw_candidates, payload.limit)
            ]
            request = MatchPreviewRequest(
                core_question=payload.core_question,
                candidates=candidates,
                table_size=payload.table_size,
            )
        except CandidateSourceError as error:
            raise HTTPException(status_code=502, detail="candidate source unavailable") from error
        except TimeoutError as error:
            raise HTTPException(status_code=502, detail="candidate source timed out") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=502, detail="candidate source returned invalid candidates") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="candidate source unavailable") from error
        request = effective_match_request(request)
        candidates = request.candidates
        plan = build_match_plan(request)
        try:
            token = source_match_tickets.issue(
                core_question=request.core_question,
                table_size=request.table_size,
                candidates=candidates,
                plan=plan,
            )
        except ValueError as error:
            raise HTTPException(status_code=503, detail="match preview temporarily unavailable") from error
        return plan.model_copy(update={"preview_token": token})

    @api.post("/matches/source-confirm", response_model=MatchedTableResponse, status_code=status.HTTP_201_CREATED)
    def confirm_source_match(payload: SourceMatchConfirmRequest) -> MatchedTableResponse:
        """Confirm one authorized source preview without re-querying the source."""
        try:
            ticket = source_match_tickets.claim(payload.preview_token)
        except ValueError as error:
            raise HTTPException(status_code=409, detail="source match preview is unavailable") from error
        selected_preferences = {
            candidate.participant_id: repo.apply_account_invitation_preference(candidate)
            for candidate in ticket.candidates
        }
        selected_ids = {seat.participant_id for seat in ticket.plan.selected}
        if any(
            selected_preferences[participant_id].roundtable_invite_preference
            is InvitationPreference.NONE
            for participant_id in selected_ids
        ):
            source_match_tickets.release(payload.preview_token)
            raise HTTPException(
                status_code=409,
                detail="a selected candidate disabled invitations after preview",
            )
        selected = [
            selected_preferences[candidate.participant_id]
            for candidate in ticket.candidates
            if candidate.participant_id in selected_ids
        ]
        # The source preview ticket is the server-side authority for this
        # confirmation. Preserve only the public signal IDs that the returned
        # MatchPlan used as evidence; never copy private candidate fields or
        # ask the client to resubmit provenance.
        origin_signal_ids = list(dict.fromkeys(
            signal_id
            for reason in ticket.plan.reasons
            for signal_id in reason.evidence_signal_ids
        ))[:20]
        table_id = payload.table_id or uuid4().hex
        try:
            state = repo.create(
                table_id,
                ticket.core_question,
                selected,
                origin_signal_ids=origin_signal_ids,
            )
        except ValueError as error:
            source_match_tickets.release(payload.preview_token)
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception:
            source_match_tickets.release(payload.preview_token)
            raise
        source_match_tickets.consume(payload.preview_token)
        return MatchedTableResponse(plan=ticket.plan, state=projected(state))

    @api.post("/matches/confirm", response_model=MatchedTableResponse, status_code=status.HTTP_201_CREATED)
    def confirm_match(payload: ConfirmMatchRequest) -> MatchedTableResponse:
        request = effective_match_request(MatchPreviewRequest(
            core_question=payload.core_question,
            candidates=payload.candidates,
            table_size=payload.table_size,
        ))
        candidates = request.candidates
        plan = build_match_plan(request)
        selected_ids = {seat.participant_id for seat in plan.selected}
        selected = [candidate for candidate in candidates if candidate.participant_id in selected_ids]
        table_id = payload.table_id or uuid4().hex
        try:
            state = repo.create(
                table_id,
                payload.core_question,
                selected,
                origin_signal_ids=payload.origin_signal_ids,
                origin_signals=payload.origin_signals,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return MatchedTableResponse(plan=plan, state=projected(state))

    @api.get("/tables/{table_id}", response_model=TableState)
    def get_table(
        table_id: str,
        request: Request,
        participant_id: str | None = Query(default=None),
    ) -> TableState:
        if participant_id is not None:
            require_request_identity(identity_resolver, request, participant_id)
        return projected(table_or_404(table_id), participant_id)

    @api.post("/tables/{table_id}/nudge", response_model=NudgeResponse)
    async def request_table_nudge(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> NudgeResponse:
        """Run the same evidence-backed cold-start nudge as WebSocket clients."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        try:
            result: NudgeResult = await run_nudge(repo, table_id, participant_id, provider)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except NudgeCooldown as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except NudgeUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        await broadcast_table_event(table_id, {
            "type": "agent_action",
            **result.action.model_dump(mode="json"),
            "gate": result.gate.model_dump(mode="json"),
            "route": result.route.model_dump(mode="json"),
        })
        await broadcast_table_state(table_id, result.state)
        return NudgeResponse(
            gate=result.gate,
            route=result.route,
            action=result.action,
            state=projected(result.state, participant_id),
        )

    @api.post("/tables/{table_id}/participants", response_model=TableState)
    async def add_participant(
        table_id: str,
        participant: ParticipantSeed,
        request: Request,
        inviter_id: str | None = Query(default=None, min_length=1),
    ) -> TableState:
        state = table_or_404(table_id)
        if state.demo is not None:
            raise HTTPException(status_code=409, detail="模拟体验固定为你、三位桌友和一位主持人")
        if identity_resolver is not None:
            if inviter_id is None:
                raise HTTPException(status_code=401, detail="inviter_id is required")
            require_request_identity(identity_resolver, request, inviter_id)
        if inviter_id is not None and inviter_id not in state.participants:
            raise HTTPException(status_code=403, detail="inviter must be a table participant")
        try:
            committed = repo.add_participant(table_id, participant)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        await broadcast_table_event(table_id, {
            "type": "participant_added",
            "participant_id": participant.participant_id,
            "state_version": committed.version,
        })
        await broadcast_table_state(table_id, committed)
        return projected(committed)

    @api.post("/tables/{table_id}/participants/{participant_id}/leave", response_model=TableState)
    async def leave_table(
        table_id: str,
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> TableState:
        """Let a participant leave without deleting the table's prior history."""
        require_request_identity(identity_resolver, request, viewer_id)
        table_or_404(table_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        if repo.get(table_id).demo is not None:
            try:
                api.state.judge_demo_service.require_owner(repo.get(table_id), participant_id)
            except PermissionError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
            await api.state.judge_demo_service.stop(table_id, closing=True)
        try:
            state = repo.remove_participant(table_id, participant_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        await broadcast_table_event(table_id, {
            "type": "participant_left",
            "participant_id": participant_id,
            "state_version": state.version,
        })
        await broadcast_table_state(table_id, state)
        return projected(state)

    @api.get("/tables/{table_id}/recruitment", response_model=TableRecruitmentDecision)
    async def get_table_recruitment_decision(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> TableRecruitmentDecision:
        """Explain to a current member whether live discussion supports recruiting now."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        return evaluate_recruitment_need(state, repo.turns(table_id))

    @api.post("/tables/{table_id}/candidate-preview", response_model=TableCandidatePreview)
    async def preview_table_candidates(
        table_id: str,
        payload: CandidatePreviewRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> TableCandidatePreview:
        """Recommend candidates for an open seat without mutating membership or invitations."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        if state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is closed")
        if state.conversation.soft_expired:
            raise HTTPException(status_code=409, detail="table is soft-expired")
        open_seats = MAX_TABLE_PARTICIPANTS - len(state.participants)
        if open_seats <= 0:
            raise HTTPException(status_code=409, detail="table has no open seats")
        recruitment = evaluate_recruitment_need(state, repo.turns(table_id))
        if candidate_source is None:
            raise HTTPException(status_code=503, detail="candidate source is not configured")
        try:
            raw_candidates = await asyncio.wait_for(
                candidate_source.search(
                    query=payload.query or recruitment.suggested_query or state.core_question,
                    limit=payload.limit,
                ),
                timeout=candidate_source_timeout_seconds,
            )
            candidates = [
                item if isinstance(item, ParticipantSeed) else ParticipantSeed.model_validate(item)
                for item in _bounded_source_rows(raw_candidates, payload.limit)
            ]
            candidates = effective_candidates(candidates)
            existing_invited = {
                item.candidate.participant_id for item in repo.invitations(table_id)
            }
            candidates = [
                item for item in candidates
                if item.participant_id not in existing_invited
                and not repo.is_no_match(participant_id, item.participant_id)
            ]
            candidate_by_id = {item.participant_id: item for item in candidates}
            recommendations = recommend_candidates(state, candidates, payload.limit)
        except CandidateSourceError as error:
            raise HTTPException(status_code=502, detail="candidate source unavailable") from error
        except TimeoutError as error:
            raise HTTPException(status_code=502, detail="candidate source timed out") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=502, detail="candidate source returned invalid candidates") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="candidate source unavailable") from error
        try:
            recommendations = [
                recommendation.model_copy(update={
                    "preview_token": candidate_invitation_tickets.issue(
                        table_id=table_id,
                        inviter_id=participant_id,
                        candidate=candidate_by_id[recommendation.participant_id],
                        reason=recommendation.reason,
                    )
                })
                for recommendation in recommendations
            ]
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="candidate invitation preview temporarily unavailable",
            ) from error
        return TableCandidatePreview(
            table_id=table_id,
            core_question=state.core_question,
            open_seats=open_seats,
            role_gaps=infer_role_gaps(person.role for person in state.participants.values()),
            recruitment=recruitment,
            candidates=recommendations,
        )

    @api.post("/tables/{table_id}/comments", response_model=PeripheralComment)
    async def add_peripheral_comment(
        table_id: str,
        payload: PeripheralCommentRequest,
        request: Request,
        author_id: str = Query(..., min_length=1),
    ) -> PeripheralComment:
        require_request_identity(identity_resolver, request, author_id)
        state = table_or_404(table_id)
        if state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is closed")
        if state.conversation.soft_expired:
            raise HTTPException(status_code=409, detail="table is soft-expired")
        comment = PeripheralComment(
            comment_id=payload.comment_id,
            table_id=table_id,
            author_id=author_id,
            display_name=payload.display_name,
            text=payload.text,
            state_version=state.version,
        )
        try:
            saved, _created = repo.append_comment_once(comment)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if _created:
            await broadcast_table_event(table_id, {
                "type": "comment_added",
                "comment": saved.model_dump(mode="json"),
                "state_version": saved.state_version,
            })
        return saved

    @api.get("/tables/{table_id}/comments", response_model=list[PeripheralComment])
    def get_peripheral_comments(table_id: str) -> list[PeripheralComment]:
        table_or_404(table_id)
        return repo.comments(table_id)

    @api.get(
        "/tables/{table_id}/comment-promotion-candidates",
        response_model=CommentPromotionCandidates,
    )
    def get_comment_promotion_candidates(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
        limit: int = Query(default=5, ge=1, le=MAX_COMMENT_PROMOTION_CANDIDATES),
    ) -> CommentPromotionCandidates:
        """Suggest safe peripheral comments while keeping promotion member-confirmed."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        if state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is closed")
        if state.conversation.soft_expired:
            raise HTTPException(status_code=409, detail="table is soft-expired")
        if state.conversation.safety_level is SafetyLevel.CRITICAL:
            raise HTTPException(status_code=409, detail="table is paused for safety review")
        return build_comment_promotion_candidates(
            state,
            repo.comments(table_id),
            repo.comment_promotions(table_id),
            limit=limit,
        )

    @api.post(
        "/tables/{table_id}/comments/{comment_id}/promote",
        response_model=CommentPromotionResponse,
    )
    async def promote_peripheral_comment(
        table_id: str,
        request: Request,
        comment_id: str = Path(..., min_length=1),
        participant_id: str = Query(..., min_length=1),
    ) -> CommentPromotionResponse:
        """Let a core member explicitly and safely bring one comment into the table."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="promoter must be a table participant")
        comment = next(
            (item for item in repo.comments(table_id) if item.comment_id == comment_id),
            None,
        )
        if comment is None:
            raise HTTPException(status_code=404, detail=f"unknown comment: {comment_id}")

        existing = next(
            (item for item in repo.comment_promotions(table_id) if item.comment_id == comment_id),
            None,
        )
        if existing is not None:
            if existing.promoter_id != participant_id:
                raise HTTPException(status_code=409, detail="comment_id is already promoted by another participant")
            turn = next(
                (item for item in repo.turns(table_id) if item.turn_id == existing.turn_id),
                None,
            )
            if turn is None:
                raise HTTPException(status_code=500, detail="comment promotion record is incomplete")
            return CommentPromotionResponse(
                comment=comment,
                promotion=existing,
                turn=turn,
                state=projected(state, participant_id),
            )

        if state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is closed")
        if state.conversation.soft_expired:
            raise HTTPException(status_code=409, detail="table is soft-expired")
        if state.conversation.safety_level.value == "critical":
            raise HTTPException(status_code=409, detail="table is paused for safety review")
        next_turn_id = max((item.turn_id for item in repo.turns(table_id)), default=0) + 1
        safety = evaluate_safety(comment.text, next_turn_id)
        if safety.blocked and safety.level is SafetyLevel.ELEVATED:
            strike_count = repo.record_safety_strike(table_id, comment.author_id)
            if strike_count < 2:
                raise HTTPException(
                    status_code=409,
                    detail="comment promotion requires a private safety reminder",
                )
            safety = escalate_boundary_safety(safety, next_turn_id)
        if safety.blocked:
            try:
                paused = repo.append_safety_state(table_id, enforce_safety(state, safety))
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            safety_broadcaster = getattr(api.state, "table_broadcast_safety", None)
            state_broadcaster = getattr(api.state, "table_broadcast_state", None)
            if safety_broadcaster is not None:
                await safety_broadcaster(table_id, safety, paused)
            if state_broadcaster is not None:
                await state_broadcaster(table_id, paused)
            raise HTTPException(status_code=422, detail="comment promotion blocked by safety policy")

        try:
            promotion, committed, _created = repo.promote_comment_once(
                table_id,
                comment_id,
                participant_id,
                expected_state_version=state.version,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        turn = next(
            (item for item in repo.turns(table_id) if item.turn_id == promotion.turn_id),
            None,
        )
        if turn is None:
            raise HTTPException(status_code=500, detail="comment promotion record is incomplete")
        broadcaster = getattr(api.state, "table_broadcast", None)
        state_broadcaster = getattr(api.state, "table_broadcast_state", None)
        if broadcaster is not None:
            await broadcaster(table_id, {
                "type": "comment_promoted",
                "comment": comment.model_dump(mode="json"),
                "promotion": promotion.model_dump(mode="json"),
                "turn": turn.model_dump(mode="json"),
            })
        if state_broadcaster is not None:
            await state_broadcaster(table_id, committed)
        return CommentPromotionResponse(
            comment=comment,
            promotion=promotion,
            turn=turn,
            state=projected(committed, participant_id),
        )

    @api.post("/tables/{table_id}/safety-reports", response_model=SafetyReport, status_code=status.HTTP_201_CREATED)
    def submit_safety_report(
        table_id: str,
        payload: SafetyReportRequest,
        request: Request,
        reporter_id: str = Query(..., min_length=1),
    ) -> SafetyReport:
        """Collect a private member report for controlled moderation review."""
        require_request_identity(identity_resolver, request, reporter_id)
        state = table_or_404(table_id)
        if reporter_id not in state.participants:
            raise HTTPException(status_code=403, detail="reporter must be a table participant")
        if payload.target_participant_id not in state.participants:
            raise HTTPException(status_code=404, detail="target must be a table participant")
        try:
            report = SafetyReport(
                table_id=table_id,
                reporter_id=reporter_id,
                state_version=state.version,
                **payload.model_dump(),
            )
            saved, _created = repo.record_safety_report(report)
            return saved
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @api.get("/tables/{table_id}/safety-reports", response_model=list[SafetyReport])
    def get_safety_reports(
        table_id: str,
        request: Request,
        reporter_id: str = Query(..., min_length=1),
    ) -> list[SafetyReport]:
        require_request_identity(identity_resolver, request, reporter_id)
        state = table_or_404(table_id)
        if reporter_id not in state.participants:
            raise HTTPException(status_code=403, detail="reporter must be a table participant")
        return repo.safety_reports(table_id, reporter_id)

    @api.get(
        "/tables/{table_id}/safety-reports/moderation",
        response_model=list[SafetyReport],
    )
    def get_moderation_safety_reports(
        table_id: str,
        request: Request,
        status_filter: Literal["open", "acknowledged", "resolved"] | None = Query(
            default=None, alias="status"
        ),
        offset: int = Query(default=0, ge=0, le=100_000),
        limit: int = Query(default=100, ge=1, le=200),
    ) -> list[SafetyReport]:
        """Expose a bounded, stable private report queue only to moderation."""
        if moderator_resolver is None:
            raise HTTPException(status_code=503, detail="moderation is not configured")
        require_moderator_identity(moderator_resolver, request)
        table_or_404(table_id)
        try:
            return repo.safety_reports(
                table_id,
                status=status_filter,
                offset=offset,
                limit=limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.get(
        "/tables/{table_id}/safety-reports/{report_id}/history",
        response_model=list[SafetyReportStatusAudit],
    )
    def get_moderation_safety_report_history(
        table_id: str,
        report_id: str,
        request: Request,
    ) -> list[SafetyReportStatusAudit]:
        """Expose one report's trusted transition chain only to moderation."""
        if moderator_resolver is None:
            raise HTTPException(status_code=503, detail="moderation is not configured")
        require_moderator_identity(moderator_resolver, request)
        table_or_404(table_id)
        if not any(item.report_id == report_id for item in repo.safety_reports(table_id)):
            raise HTTPException(status_code=404, detail=f"unknown safety report: {report_id}")
        return repo.safety_report_audits(table_id, report_id)

    @api.patch(
        "/tables/{table_id}/safety-reports/{report_id}",
        response_model=SafetyReport,
    )
    def update_moderation_safety_report(
        table_id: str,
        report_id: str,
        payload: SafetyReportStatusRequest,
        request: Request,
    ) -> SafetyReport:
        """Advance a private report only through the trusted moderation boundary."""
        if moderator_resolver is None:
            raise HTTPException(status_code=503, detail="moderation is not configured")
        moderator_id = require_moderator_identity(moderator_resolver, request)
        table_or_404(table_id)
        try:
            return repo.update_safety_report_status(
                table_id,
                report_id,
                payload.status,
                moderator_id=moderator_id,
                reason=payload.reason,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @api.post(
        "/tables/{table_id}/safety/resolve",
        response_model=SafetyResolutionResponse,
    )
    async def resolve_safety(
        table_id: str,
        payload: SafetyResolutionRequest,
        request: Request,
    ) -> SafetyResolutionResponse:
        """Let a trusted moderation adapter resume or remove after a hard pause."""
        if moderator_resolver is None:
            raise HTTPException(status_code=503, detail="moderation is not configured")
        moderator_id = require_moderator_identity(moderator_resolver, request)
        table_or_404(table_id)
        try:
            state, resolution = repo.resolve_safety(
                table_id,
                payload.action,
                moderator_id,
                payload.reason,
                payload.participant_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        broadcaster = getattr(api.state, "table_broadcast", None)
        state_broadcaster = getattr(api.state, "table_broadcast_state", None)
        if broadcaster is not None:
            await broadcaster(table_id, {
                "type": "safety_resolved",
                "action": resolution.action,
                "participant_id": resolution.participant_id,
                "state_version": resolution.state_version,
            })
        if state_broadcaster is not None:
            await state_broadcaster(table_id, state)
        return SafetyResolutionResponse(
            resolution=resolution,
            state=project_state_for_viewer(state, None),
        )

    @api.get(
        "/tables/{table_id}/safety/resolutions",
        response_model=list[SafetyResolution],
    )
    def get_safety_resolutions(
        table_id: str,
        request: Request,
    ) -> list[SafetyResolution]:
        """Expose the safety-resolution audit only to the moderation adapter."""
        if moderator_resolver is None:
            raise HTTPException(status_code=503, detail="moderation is not configured")
        require_moderator_identity(moderator_resolver, request)
        table_or_404(table_id)
        return repo.safety_resolutions(table_id)

    def invitation_view(invitation) -> InvitationView:
        candidate = invitation.candidate
        return InvitationView(
            invitation_id=invitation.invitation_id,
            table_id=invitation.table_id,
            participant_id=candidate.participant_id,
            display_name=candidate.display_name,
            role=candidate.role,
            reason=invitation.reason,
            status=invitation.status,
        )

    def invitation_inbox_item(invitation: Invitation) -> InvitationInboxItem:
        """Combine a private candidate-owned invite with a public Lobby card."""
        state = repo.get(invitation.table_id)
        reason = None
        if invitation.status is not InvitationStatus.PENDING:
            reason = "invitation_processed"
        elif state.conversation.closed:
            reason = "table_closed"
        elif state.conversation.soft_expired:
            reason = "table_soft_expired"
        elif invitation.candidate.participant_id in state.participants:
            reason = "candidate_already_joined"
        elif len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            reason = "table_full"
        elif any(
            repo.is_no_match(member_id, invitation.candidate.participant_id)
            for member_id in state.participants
        ):
            reason = "matching_disabled"
        return InvitationInboxItem(
            invitation=invitation_view(invitation),
            table=build_lobby_preview(state),
            can_respond=reason is None,
            unavailable_reason=reason,
        )

    def join_request_view(join_request: JoinRequest) -> JoinRequestView:
        """Project a request without exposing the candidate's private profile."""
        candidate = join_request.candidate
        return JoinRequestView(
            request_id=join_request.request_id,
            table_id=join_request.table_id,
            participant_id=candidate.participant_id,
            display_name=candidate.display_name,
            role=candidate.role,
            message=join_request.message,
            status=join_request.status,
            invitation_id=join_request.invitation_id,
        )

    @api.post(
        "/tables/{table_id}/join-requests",
        response_model=JoinRequestView,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_join_request(
        table_id: str,
        payload: JoinRequestCreateRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> JoinRequestView:
        """Let a routed candidate ask to be considered without granting a seat."""
        require_request_identity(identity_resolver, request, participant_id)
        if payload.candidate.participant_id != participant_id:
            raise HTTPException(status_code=403, detail="candidate does not match participant_id")
        state = table_or_404(table_id)
        try:
            join_request, created = repo.create_join_request(
                JoinRequest(
                    request_id=payload.request_id,
                    table_id=table_id,
                    candidate=payload.candidate,
                    message=payload.message,
                )
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        view = join_request_view(join_request)
        if created:
            await broadcast_table_event(table_id, {
                "type": "join_request_created",
                "request": view.model_dump(mode="json"),
                "state_version": state.version,
            })
        return view

    @api.get(
        "/tables/{table_id}/join-requests",
        response_model=list[JoinRequestView],
    )
    def get_join_requests(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> list[JoinRequestView]:
        """Members see the redacted queue; candidates see only their own request."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        rows = repo.join_requests(table_id)
        if participant_id not in state.participants:
            rows = [
                item for item in rows
                if item.candidate.participant_id == participant_id
            ]
        return [join_request_view(item) for item in rows]

    @api.post(
        "/tables/{table_id}/join-requests/{request_id}/approve",
        response_model=JoinRequestApprovalResponse,
    )
    async def approve_join_request(
        table_id: str,
        request_id: str,
        payload: JoinRequestApproveRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> JoinRequestApprovalResponse:
        """Turn member approval into an invitation; acceptance remains separate."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        try:
            join_request, invitation = repo.approve_join_request(
                table_id, request_id, participant_id, payload.reason
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        request_view = join_request_view(join_request)
        invitation_preview = invitation_view(invitation)
        await broadcast_table_event(table_id, {
            "type": "join_request_approved",
            "request": request_view.model_dump(mode="json"),
            "invitation": invitation_preview.model_dump(mode="json"),
            "state_version": state.version,
        })
        return JoinRequestApprovalResponse(
            request=request_view,
            invitation=invitation_preview,
        )

    @api.post(
        "/tables/{table_id}/join-requests/{request_id}/decline",
        response_model=JoinRequestView,
    )
    async def decline_join_request(
        table_id: str,
        request_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> JoinRequestView:
        """Decline a request while retaining a bounded audit trail."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        try:
            join_request = repo.decline_join_request(table_id, request_id, participant_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        view = join_request_view(join_request)
        await broadcast_table_event(table_id, {
            "type": "join_request_declined",
            "request": view.model_dump(mode="json"),
            "state_version": state.version,
        })
        return view

    @api.post("/tables/{table_id}/invitations", response_model=InvitationView, status_code=status.HTTP_201_CREATED)
    async def create_invitation(
        table_id: str,
        payload: CreateInvitationRequest,
        request: Request,
        inviter_id: str = Query(..., min_length=1),
    ) -> InvitationView:
        require_request_identity(identity_resolver, request, inviter_id)
        state = table_or_404(table_id)
        try:
            invitation = repo.create_invitation(
                table_id, inviter_id, payload.candidate, payload.reason
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        view = invitation_view(invitation)
        await broadcast_table_event(table_id, {
            "type": "invitation_updated",
            "invitation": view.model_dump(mode="json"),
            "state_version": state.version,
        })
        return view

    @api.post(
        "/tables/{table_id}/invitations/from-preview",
        response_model=InvitationView,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_invitation_from_preview(
        table_id: str,
        payload: PreviewInvitationRequest,
        request: Request,
        inviter_id: str = Query(..., min_length=1),
    ) -> InvitationView:
        """Turn a server-held candidate recommendation into an invitation."""
        require_request_identity(identity_resolver, request, inviter_id)
        table_or_404(table_id)
        try:
            ticket = candidate_invitation_tickets.claim(payload.preview_token)
        except ValueError as error:
            raise HTTPException(
                status_code=409,
                detail="candidate invitation preview is unavailable",
            ) from error
        if ticket.table_id != table_id:
            candidate_invitation_tickets.release(payload.preview_token)
            raise HTTPException(status_code=409, detail="candidate invitation preview is unavailable")
        if ticket.inviter_id != inviter_id:
            candidate_invitation_tickets.release(payload.preview_token)
            raise HTTPException(status_code=403, detail="preview ticket belongs to another inviter")
        try:
            invitation = repo.create_invitation(
                table_id,
                inviter_id,
                ticket.candidate,
                payload.reason or ticket.reason,
            )
        except PermissionError as error:
            candidate_invitation_tickets.release(payload.preview_token)
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            candidate_invitation_tickets.release(payload.preview_token)
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception:
            candidate_invitation_tickets.release(payload.preview_token)
            raise
        candidate_invitation_tickets.consume(payload.preview_token)
        view = invitation_view(invitation)
        state = table_or_404(table_id)
        await broadcast_table_event(table_id, {
            "type": "invitation_updated",
            "invitation": view.model_dump(mode="json"),
            "state_version": state.version,
        })
        return view

    @api.get("/tables/{table_id}/invitations", response_model=list[InvitationView])
    def get_invitations(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> list[InvitationView]:
        require_request_identity(identity_resolver, request, participant_id)
        table_or_404(table_id)
        return [
            invitation_view(invitation)
            for invitation in repo.invitations(table_id)
            if invitation.candidate.participant_id == participant_id
        ]

    @api.get(
        "/participants/{participant_id}/invitations",
        response_model=InvitationInboxResponse,
    )
    def get_participant_invitation_inbox(
        participant_id: str,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
        invitation_status: InvitationStatus | None = Query(default=None, alias="status"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
    ) -> InvitationInboxResponse:
        """List only the authenticated candidate's invitations across all tables."""
        require_request_identity(identity_resolver, request, viewer_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        refresh_sync_windows()
        try:
            rows = repo.participant_invitations(participant_id, invitation_status)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return InvitationInboxResponse(
            participant_id=participant_id,
            items=[invitation_inbox_item(item) for item in rows[offset:offset + limit]],
            total=len(rows),
            offset=offset,
            limit=limit,
        )

    @api.post(
        "/tables/{table_id}/invitations/{invitation_id}/respond",
        response_model=InvitationResponse,
    )
    async def respond_invitation(
        table_id: str,
        invitation_id: str,
        payload: RespondInvitationRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> InvitationResponse:
        require_request_identity(identity_resolver, request, participant_id)
        current_state = table_or_404(table_id)
        existing_invitation = next(
            (item for item in repo.invitations(table_id) if item.invitation_id == invitation_id),
            None,
        )
        was_pending = existing_invitation is not None and existing_invitation.status.value == "pending"
        try:
            invitation, state = repo.respond_invitation(
                table_id, invitation_id, participant_id, payload.accept
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        projected_state = project_state_for_viewer(state, participant_id) if state is not None else None
        view = invitation_view(invitation)
        if was_pending:
            await broadcast_table_event(table_id, {
                "type": "invitation_updated",
                "invitation": view.model_dump(mode="json"),
                "state_version": state.version if state is not None else current_state.version,
            })
        if state is not None and was_pending:
            await broadcast_table_event(table_id, {
                "type": "participant_added",
                "participant_id": participant_id,
                "state_version": state.version,
            })
            await broadcast_table_state(table_id, state)
        return InvitationResponse(
            invitation=view, state=projected_state
        )

    def sync_decision(table_id: str, participant_id: str, signals: SyncUpgradeSignals) -> SyncUpgradeDecision:
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        return evaluate_sync_upgrade(state, signals)

    @api.post("/tables/{table_id}/sync/preview", response_model=SyncUpgradeDecision)
    def preview_sync_upgrade(
        table_id: str,
        signals: SyncUpgradeSignals,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> SyncUpgradeDecision:
        require_request_identity(identity_resolver, request, participant_id)
        return sync_decision(table_id, participant_id, signals)

    @api.post("/tables/{table_id}/sync/upgrade", response_model=SyncUpgradeResponse)
    async def upgrade_to_sync(
        table_id: str,
        signals: SyncUpgradeSignals,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> SyncUpgradeResponse:
        require_request_identity(identity_resolver, request, participant_id)
        decision = sync_decision(table_id, participant_id, signals)
        previous_state = table_or_404(table_id)
        if not decision.eligible:
            raise HTTPException(status_code=409, detail=decision.model_dump(mode="json"))
        try:
            state = repo.upgrade_to_sync(
                table_id,
                sync_expires_at=clock() + sync_window_seconds,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if state.version != previous_state.version:
            await broadcast_table_event(table_id, {
                "type": "table_mode_changed",
                "mode": state.conversation.mode.value,
                "state_version": state.version,
            })
            await broadcast_table_state(table_id, state)
        return SyncUpgradeResponse(decision=decision, state=projected(state, participant_id))

    @api.post("/tables/{table_id}/participants/{participant_id}/consent", response_model=TableState)
    async def set_participant_consent(
        table_id: str,
        participant_id: str,
        payload: ParticipantConsentRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> TableState:
        require_request_identity(identity_resolver, request, viewer_id)
        previous_state = table_or_404(table_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            state = repo.set_profile_consent(table_id, participant_id, payload.profile_shared)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if state.version != previous_state.version:
            await broadcast_table_event(table_id, {
                "type": "participant_consent_changed",
                "participant_id": participant_id,
                "profile_shared": payload.profile_shared,
                "state_version": state.version,
            })
            await broadcast_table_state(table_id, state)
        return projected(state, participant_id)

    @api.put(
        "/tables/{table_id}/participants/{participant_id}/invitation-preference",
        response_model=TableState,
    )
    async def set_participant_invitation_preference(
        table_id: str,
        participant_id: str,
        payload: ParticipantInvitationPreferenceRequest,
        request: Request,
        viewer_id: str = Query(..., min_length=1),
    ) -> TableState:
        require_request_identity(identity_resolver, request, viewer_id)
        previous_state = table_or_404(table_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            state = repo.set_invitation_preference(
                table_id, participant_id, payload.preference
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if state.version != previous_state.version:
            await broadcast_table_event(table_id, {
                "type": "participant_invitation_preference_changed",
                "participant_id": participant_id,
                "preference": payload.preference.value,
                "state_version": state.version,
            })
            await broadcast_table_state(table_id, state)
        return projected(state, participant_id)

    @api.get("/tables/{table_id}/state", response_model=TableState)
    def get_state(
        table_id: str,
        request: Request,
        participant_id: str | None = Query(default=None),
    ) -> TableState:
        if participant_id is not None:
            require_request_identity(identity_resolver, request, participant_id)
        return projected(table_or_404(table_id), participant_id)

    @api.get("/tables/{table_id}/replay", response_model=ReplayResponse)
    def get_replay(
        table_id: str,
        request: Request,
        from_version: int | None = Query(default=None, ge=0),
        participant_id: str | None = Query(default=None),
    ) -> ReplayResponse:
        if identity_resolver is not None:
            if participant_id is None:
                raise HTTPException(status_code=401, detail="participant_id is required")
            require_request_identity(identity_resolver, request, participant_id)
        elif participant_id is not None:
            require_request_identity(identity_resolver, request, participant_id)
        current_state = table_or_404(table_id)
        if current_state.demo is not None and participant_id != current_state.demo.owner_participant_id:
            raise HTTPException(status_code=403, detail="只有本次体验的参与者可以读取聊天记录")
        if participant_id is not None and participant_id not in current_state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {participant_id}")
        try:
            snapshots = repo.replay(table_id, from_version)
            return ReplayResponse(
                table_id=table_id,
                messages=repo.turns(table_id),
                snapshots=[project_state_for_viewer(item, participant_id) for item in snapshots],
                interventions=repo.interventions(table_id),
                comments=repo.comments(table_id),
                comment_promotions=repo.comment_promotions(table_id),
                source_signals=repo.public_source_signals(table_id),
                stage_summaries=repo.stage_summaries(table_id),
                summary_feedback=[
                    item for item in repo.summary_feedback(table_id)
                    if participant_id is not None and item.participant_id == participant_id
                ],
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @api.get("/tables/{table_id}/stage-summaries", response_model=list[StageSummary])
    def get_stage_summaries(
        table_id: str,
        request: Request,
        participant_id: str | None = Query(default=None, min_length=1),
    ) -> list[StageSummary]:
        state = table_or_404(table_id)
        if identity_resolver is not None:
            if participant_id is None:
                raise HTTPException(status_code=401, detail="participant_id is required")
            require_request_identity(identity_resolver, request, participant_id)
        if participant_id is not None and participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        return repo.stage_summaries(table_id)

    @api.get("/tables/{table_id}/stage-summaries/latest", response_model=StageSummary)
    def get_latest_stage_summary(
        table_id: str,
        request: Request,
        participant_id: str | None = Query(default=None, min_length=1),
    ) -> StageSummary:
        rows = get_stage_summaries(table_id, request, participant_id)
        if not rows:
            raise HTTPException(status_code=404, detail="no published stage summary")
        return next((item for item in reversed(rows) if item.status == "published"), rows[-1])

    @api.post(
        "/tables/{table_id}/stage-summaries/request",
        response_model=StageSummaryRequestResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def request_stage_summary(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> StageSummaryRequestResponse:
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        if state.conversation.closed or state.conversation.soft_expired:
            raise HTTPException(status_code=409, detail="table is not active")
        if state.conversation.safety_level is SafetyLevel.CRITICAL:
            raise HTTPException(status_code=409, detail="table is paused for safety review")
        if not repo.turns(table_id):
            raise HTTPException(status_code=409, detail="summary requires at least one committed turn")
        service: TableRunService = api.state.table_run_service
        await service.enqueue(table_id, manual=True)
        return StageSummaryRequestResponse(table_id=table_id, accepted=True, state_version=state.version)

    @api.post(
        "/tables/{table_id}/stage-summaries/{summary_id}/feedback",
        response_model=StageSummaryFeedback,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_stage_summary_feedback(
        table_id: str,
        summary_id: str,
        payload: StageSummaryFeedbackRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
        summary_revision: int = Query(..., ge=1),
    ) -> StageSummaryFeedback:
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        try:
            feedback = StageSummaryFeedback(
                feedback_id=f"{table_id}:feedback:{summary_id}:{summary_revision}:{participant_id}",
                table_id=table_id,
                summary_id=summary_id,
                summary_revision=summary_revision,
                participant_id=participant_id,
                kind=payload.kind,
                note=payload.note,
                evidence_turns=payload.evidence_turns,
                created_at=clock(),
            )
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="请写下需要修改的内容") from error
        try:
            saved, created = repo.append_summary_feedback(feedback)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if created:
            await broadcast_table_event(table_id, {
                "type": "stage_summary_feedback",
                "feedback": saved.model_dump(mode="json"),
            })
            latest = repo.latest_stage_summary(table_id)
            if latest is not None and latest.summary_id == saved.summary_id and latest.revision == saved.summary_revision:
                try:
                    revised, saved, revised_state = repo.apply_summary_feedback_revision(
                        table_id, saved.feedback_id
                    )
                except ValueError as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                await broadcast_table_event(table_id, {
                    "type": "stage_summary_published",
                    "summary": revised.model_dump(mode="json"),
                    "reason": "member_feedback",
                })
                await broadcast_table_state(table_id, revised_state)
        return saved

    @api.get("/tables/{table_id}/agent-runs", response_model=list[AgentRunRecord])
    def get_agent_runs(
        table_id: str,
        request: Request,
    ) -> list[AgentRunRecord]:
        if moderator_resolver is None:
            raise HTTPException(status_code=403, detail="agent run ledger is restricted")
        require_moderator_identity(moderator_resolver, request)
        table_or_404(table_id)
        return repo.agent_runs(table_id)

    @api.get("/tables/{table_id}/lineage", response_model=TableLineageResponse)
    def get_lineage(table_id: str) -> TableLineageResponse:
        """Return the bounded public question lineage for one table."""
        table_or_404(table_id)
        try:
            items = repo.lineage(table_id)
            return TableLineageResponse(
                table_id=table_id,
                items=[
                    TableLineageItem(
                        table_id=item.table_id,
                        origin_table_id=item.origin_table_id,
                        version=item.version,
                        core_question=item.core_question,
                        origin_signal_ids=item.origin_signal_ids,
                        source_signals=repo.public_source_signals(item.table_id),
                    )
                    for item in items
                ],
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @api.get("/tables/{table_id}/interventions", response_model=list[InterventionRecord])
    def get_interventions(
        table_id: str,
        request: Request,
        participant_id: str | None = Query(default=None, min_length=1),
    ) -> list[InterventionRecord]:
        state = table_or_404(table_id)
        if identity_resolver is not None:
            if participant_id is None:
                raise HTTPException(status_code=401, detail="participant_id is required")
            require_request_identity(identity_resolver, request, participant_id)
        if participant_id is not None and participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        return repo.interventions(table_id)

    def close_follow_ups(table_id: str, participant_id: str) -> tuple[TableState, list[FollowUpItem], dict[int, FollowUpOutcome]]:
        state = table_or_404(table_id)
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        if participant_id not in state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {participant_id}")
        try:
            baseline = build_shared_baseline(state, turns=repo.turns(table_id), latest_summary=repo.latest_stage_summary(table_id))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        outcomes = {item.follow_up_index: item for item in repo.follow_up_outcomes(table_id)}
        return state, baseline.collective_next_steps, outcomes

    @api.get("/tables/{table_id}/follow-ups", response_model=list[FollowUpStatusResponse])
    def get_follow_ups(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> list[FollowUpStatusResponse]:
        require_request_identity(identity_resolver, request, participant_id)
        _state, items, outcomes = close_follow_ups(table_id, participant_id)
        return [
            FollowUpStatusResponse(
                follow_up_index=index,
                item=item,
                outcome=outcomes.get(index),
            )
            for index, item in enumerate(items)
        ]

    @api.post(
        "/tables/{table_id}/follow-ups/{follow_up_index}/outcome",
        response_model=FollowUpStatusResponse,
    )
    def report_follow_up_outcome(
        table_id: str,
        request: Request,
        follow_up_index: int = Path(..., ge=0),
        payload: FollowUpOutcomeRequest = ...,
        participant_id: str = Query(..., min_length=1),
    ) -> FollowUpStatusResponse:
        require_request_identity(identity_resolver, request, participant_id)
        _state, items, outcomes = close_follow_ups(table_id, participant_id)
        if follow_up_index >= len(items):
            raise HTTPException(status_code=404, detail="unknown follow-up item")
        item = items[follow_up_index]
        if item.is_commitment and item.owner_participant_id != participant_id:
            raise HTTPException(status_code=403, detail="only the commitment owner may report its outcome")
        existing = outcomes.get(follow_up_index)
        if existing is not None and existing.participant_id != participant_id:
            raise HTTPException(status_code=403, detail="follow-up outcome already belongs to another participant")
        outcome = FollowUpOutcome(
            table_id=table_id,
            follow_up_index=follow_up_index,
            participant_id=participant_id,
            status=payload.status,
            note=payload.note,
        )
        try:
            saved = repo.record_follow_up_outcome(outcome)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return FollowUpStatusResponse(follow_up_index=follow_up_index, item=item, outcome=saved)

    def feedback_summary(table_id: str, participant_id: str) -> FeedbackSummary:
        state = table_or_404(table_id)
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        rows = repo.value_feedback(table_id)

        def average(field: str) -> float | None:
            if not rows:
                return None
            return round(sum(getattr(item, field) for item in rows) / len(rows), 2)

        return FeedbackSummary(
            table_id=table_id,
            state_version=state.version,
            eligible_participant_count=len(state.participants),
            response_count=len(rows),
            cognitive_average=average("cognitive_value"),
            relationship_average=average("relationship_value"),
            action_average=average("action_value"),
            emotional_average=average("emotional_value"),
            would_join_again_count=sum(item.would_join_again for item in rows),
        )

    @api.get("/tables/{table_id}/evaluation", response_model=TableEvaluation)
    def get_table_evaluation(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> TableEvaluation:
        """Return privacy-safe, member-scoped metrics for the current table."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")

        turns = repo.turns(table_id)
        interventions = repo.interventions(table_id)
        snapshot_phases = {
            snapshot.version: snapshot.phase for snapshot in repo.replay(table_id)
        }
        intervention_phase_counts = {phase: 0 for phase in Phase}
        for intervention in interventions:
            phase = snapshot_phases.get(intervention.state_version)
            if phase is not None:
                intervention_phase_counts[phase] += 1
        invitations = repo.invitations(table_id)
        invitation_count = len(invitations)
        invitation_pending_count = sum(item.status.value == "pending" for item in invitations)
        invitation_accepted_count = sum(item.status.value == "accepted" for item in invitations)
        invitation_declined_count = sum(item.status.value == "declined" for item in invitations)
        comments = repo.comments(table_id)
        promoted_comments = repo.comment_promotions(table_id)
        follow_up_items: list[FollowUpItem] = []
        if state.conversation.closed:
            try:
                follow_up_items = build_shared_baseline(state, turns=turns, latest_summary=repo.latest_stage_summary(table_id)).collective_next_steps
            except ValueError:
                # A legacy/direct repository close may lack evidence for a baseline;
                # evaluation remains readable and reports no close-card actions.
                follow_up_items = []
        outcomes = repo.follow_up_outcomes(table_id)
        valid_outcomes = [
            item for item in outcomes if 0 <= item.follow_up_index < len(follow_up_items)
        ]
        completed_outcomes = sum(item.status == "completed" for item in valid_outcomes)
        feedback = feedback_summary(table_id, participant_id) if state.conversation.closed else None
        response_count = feedback.response_count if feedback is not None else 0
        feedback_completion_rate = round(response_count / len(state.participants), 2) if state.participants else 0.0

        return TableEvaluation(
            table_id=table_id,
            state_version=state.version,
            phase=state.phase,
            closed=state.conversation.closed,
            participant_count=len(state.participants),
            invitation_count=invitation_count,
            invitation_pending_count=invitation_pending_count,
            invitation_accepted_count=invitation_accepted_count,
            invitation_declined_count=invitation_declined_count,
            invitation_acceptance_rate=(
                round(invitation_accepted_count / invitation_count, 2)
                if invitation_count else None
            ),
            peripheral_comment_count=len(comments),
            promoted_comment_count=len(promoted_comments),
            human_turn_count=len(turns),
            intervention_count=len(interventions),
            reflected_intervention_count=sum(item.reflection is not None for item in interventions),
            effective_intervention_count=sum(
                item.reflection_effective is True
                for item in interventions
            ),
            intervention_rate=(round(len(interventions) / len(turns), 2)) if turns else 0.0,
            effective_intervention_rate=(
                sum(item.reflection_effective is True for item in interventions)
                / sum(item.reflection is not None for item in interventions)
                if any(item.reflection is not None for item in interventions) else None
            ),
            intervention_phase_counts=intervention_phase_counts,
            follow_up_count=len(follow_up_items),
            follow_up_reported_count=len(valid_outcomes),
            follow_up_completed_count=completed_outcomes,
            follow_up_completion_rate=(
                round(completed_outcomes / len(follow_up_items), 2)
                if follow_up_items else None
            ),
            feedback_completion_rate=feedback_completion_rate,
            would_join_again_rate=(
                round(feedback.would_join_again_count / response_count, 2)
                if response_count else None
            ),
            feedback_summary=feedback,
        )

    @api.post("/tables/{table_id}/feedback", response_model=ValueFeedback)
    def submit_value_feedback(
        table_id: str,
        payload: ValueFeedbackRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> ValueFeedback:
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        feedback = ValueFeedback(
            table_id=table_id,
            participant_id=participant_id,
            state_version=state.version,
            **payload.model_dump(),
        )
        try:
            return repo.record_value_feedback(feedback)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @api.get("/tables/{table_id}/feedback", response_model=FeedbackSummary)
    def get_value_feedback(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> FeedbackSummary:
        require_request_identity(identity_resolver, request, participant_id)
        return feedback_summary(table_id, participant_id)

    @api.post("/tables/{table_id}/soft-expire", response_model=TableState)
    async def soft_expire_table(
        table_id: str,
        payload: SoftExpireRequest,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> TableState:
        """Hide a stale table from discovery while preserving its history and close path."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        try:
            expired = repo.soft_expire_table(table_id, payload.reason)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if expired.version != state.version:
            await broadcast_table_event(table_id, {
                "type": "table_soft_expired",
                "reason": expired.conversation.soft_expiry_reason,
                "state_version": expired.version,
            })
            await broadcast_table_state(table_id, expired)
        return projected(expired, participant_id)

    @api.post("/tables/{table_id}/close", response_model=SharedBaseline)
    async def close_table(
        table_id: str,
        request: Request,
        participant_id: str | None = Query(default=None, min_length=1),
    ) -> SharedBaseline:
        state = table_or_404(table_id)
        if identity_resolver is not None:
            if participant_id is None:
                raise HTTPException(status_code=401, detail="participant_id is required")
            require_request_identity(identity_resolver, request, participant_id)
        if participant_id is not None and participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        if state.demo is not None:
            try:
                api.state.judge_demo_service.require_owner(state, participant_id or "")
            except PermissionError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
            await api.state.judge_demo_service.stop(table_id, closing=True)
        if not state.conversation.closed:
            await broadcast_table_event(table_id, {
                "type": "close_started",
                "table_id": table_id,
                "state_version": state.version,
                "reason": "rest_requested_close",
            })
        try:
            service: TableRunService = api.state.table_run_service
            if not state.conversation.closed and repo.turns(table_id):
                await service.enqueue(table_id, pre_close=True, silent=True)
                await service.wait_idle(table_id)
                state = repo.get(table_id)
            latest_summary = repo.latest_stage_summary(table_id)
            build_shared_baseline(state, turns=repo.turns(table_id), latest_summary=latest_summary)
            closed = (
                repo.close_table_for_participant(table_id, participant_id)
                if participant_id is not None
                else repo.close_table(table_id)
            )
            baseline = build_shared_baseline(closed, turns=repo.turns(table_id), latest_summary=latest_summary)
        except ValueError as error:
            if state.demo is not None:
                await api.state.judge_demo_service.abort_close(table_id)
            raise HTTPException(status_code=409, detail=str(error)) from error
        if closed.version != state.version:
            await broadcast_table_event(table_id, {
                "type": "table_closed",
                "state_version": closed.version,
            })
            await broadcast_table_state(table_id, closed)
        return baseline

    @api.post(
        "/tables/{table_id}/recompose",
        response_model=RecomposeTableResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def recompose_table(
        table_id: str,
        payload: RecomposeTableRequest,
        request: Request,
        participant_id: str | None = Query(default=None, min_length=1),
    ) -> RecomposeTableResponse:
        """Create a new table from a closed table's evolved question and chosen seeds."""
        state = table_or_404(table_id)
        if identity_resolver is not None:
            if participant_id is None:
                raise HTTPException(status_code=401, detail="participant_id is required")
            require_request_identity(identity_resolver, request, participant_id)
        if participant_id is not None and participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        try:
            baseline = build_shared_baseline(state, turns=repo.turns(table_id), latest_summary=repo.latest_stage_summary(table_id))
            new_table_id = payload.table_id or uuid4().hex
            new_state = repo.create(
                new_table_id,
                baseline.evolved_question.text,
                payload.participants,
                origin_table_id=table_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return RecomposeTableResponse(
            source_table_id=table_id,
            source_state_version=state.version,
            new_table_id=new_table_id,
            evolved_question=baseline.evolved_question,
            state=projected(new_state),
        )

    @api.get("/tables/{table_id}/close-artifacts", response_model=CloseArtifactsResponse)
    def get_close_artifacts(
        table_id: str,
        request: Request,
        participant_id: str = Query(..., min_length=1),
    ) -> CloseArtifactsResponse:
        """Rebuild the evidence-backed close card after reconnect/restart."""
        require_request_identity(identity_resolver, request, participant_id)
        state = table_or_404(table_id)
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        if participant_id not in state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {participant_id}")
        try:
            latest_summary = repo.latest_stage_summary(table_id)
            baseline = build_shared_baseline(state, turns=repo.turns(table_id), latest_summary=latest_summary)
            personal = build_personal_card(state, participant_id, latest_summary=latest_summary)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return CloseArtifactsResponse(
            table_id=table_id,
            state_version=state.version,
            shared_baseline=baseline,
            personal_card=personal,
        )

    return api


app = create_app()
