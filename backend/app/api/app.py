"""Minimal REST API for one explainable conversation table."""

import asyncio
import os
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.domain import CommentPromotion, ContentSignal, FeedbackSummary, FollowUpItem, FollowUpOutcome, HumanTurn, InvitationView, InterventionRecord, MatchPlan, MatchRequest, NoMatchPreference, OpportunityPreview, OpportunityRequest, ParticipantSeed, PeripheralComment, PersonalCard, PersonalContextConsent, PersonalContextPreview, PersonalContextScope, PersonalContextSignal, RelationshipMemory, SafetyReport, SharedBaseline, SyncUpgradeDecision, SyncUpgradeSignals, TableCandidatePreview, TableState, ValueFeedback
from app.matching import build_match_plan, infer_role_gaps, recommend_candidates
from app.opportunities import build_opportunity_preview
from app.orchestrator import build_personal_card, build_shared_baseline, enforce_safety, evaluate_safety, evaluate_sync_upgrade
from app.providers import LLMProvider
from app.domain.schemas import EvidenceStatement

from .repository import MAX_TABLE_PARTICIPANTS, InMemoryTableRepository
from .privacy import project_state_for_viewer
from .websocket import register_websocket_routes
from app.sources import CandidateSource, CandidateSourceError, ContentSignalSource, ContentSignalSourceError, PersonalContextSource, PersonalContextSourceError
from app.personal import build_personal_context_preview


class CreateTableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str | None = Field(default=None, min_length=1)
    core_question: str = Field(min_length=1)
    participants: list[ParticipantSeed] = Field(default_factory=list)


class ReplayResponse(BaseModel):
    """A replay keeps the original messages beside explainable state snapshots."""

    model_config = ConfigDict(extra="forbid")

    table_id: str
    messages: list[HumanTurn]
    snapshots: list[TableState]
    interventions: list[InterventionRecord] = Field(default_factory=list)
    comments: list[PeripheralComment] = Field(default_factory=list)
    comment_promotions: list[CommentPromotion] = Field(default_factory=list)


class ParticipantConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_shared: bool


class CreateInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: ParticipantSeed
    reason: str = Field(min_length=1, max_length=240)


class RespondInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: bool


class InvitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation: InvitationView
    state: TableState | None = None


class SyncUpgradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: SyncUpgradeDecision
    state: TableState


class ConfirmMatchRequest(MatchRequest):
    table_id: str | None = Field(default=None, min_length=1)


class SourceMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_question: str = Field(min_length=1)
    query: str | None = Field(default=None, min_length=1)
    table_size: int = Field(default=4, ge=2, le=5)
    limit: int = Field(default=20, ge=2, le=20)


class CandidatePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, min_length=1, max_length=120)
    limit: int = Field(default=10, ge=1, le=20)


class OpportunitySourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=20, ge=2, le=20)


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
) -> FastAPI:
    """Create an app with an injectable repository for tests and future persistence."""
    if candidate_source_timeout_seconds <= 0:
        raise ValueError("candidate_source_timeout_seconds must be positive")
    if content_source_timeout_seconds <= 0:
        raise ValueError("content_source_timeout_seconds must be positive")
    if personal_context_source_timeout_seconds <= 0:
        raise ValueError("personal_context_source_timeout_seconds must be positive")
    repo = repository or InMemoryTableRepository()
    api = FastAPI(title="组一桌 Conversation Orchestrator")
    api.state.repository = repo
    api.state.provider = provider
    api.state.candidate_source = candidate_source
    api.state.content_source = content_source
    api.state.personal_context_source = personal_context_source
    raw_origins = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["DELETE", "GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    register_websocket_routes(api, repo, provider)

    @api.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready", "repository": type(repo).__name__}

    def table_or_404(table_id: str) -> TableState:
        try:
            return repo.get(table_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    def projected(state: TableState, participant_id: str | None = None) -> TableState:
        if participant_id is not None and participant_id not in state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {participant_id}")
        return project_state_for_viewer(state, participant_id)

    @api.post("/tables", response_model=TableState, status_code=status.HTTP_201_CREATED)
    def create_table(payload: CreateTableRequest) -> TableState:
        table_id = payload.table_id or uuid4().hex
        try:
            return projected(repo.create(table_id, payload.core_question, payload.participants))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @api.get("/tables", response_model=list[TableState])
    def list_tables(
        participant_id: str | None = Query(default=None),
        include_closed: bool = Query(default=False),
    ) -> list[TableState]:
        return [
            project_state_for_viewer(state, participant_id)
            for state in repo.list_tables(include_closed=include_closed)
        ]

    @api.get("/participants/{participant_id}/relationship-memory", response_model=list[RelationshipMemory])
    def get_relationship_memory(
        participant_id: str,
        viewer_id: str = Query(..., min_length=1),
    ) -> list[RelationshipMemory]:
        """Return evidence-backed old-table reminders only to the participant themselves."""
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        return repo.relationship_memories(participant_id)

    @api.put(
        "/participants/{participant_id}/personal-context/consent",
        response_model=PersonalContextConsent,
    )
    def grant_personal_context_consent(
        participant_id: str,
        payload: PersonalContextConsentRequest,
        viewer_id: str = Query(..., min_length=1),
    ) -> PersonalContextConsent:
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
        viewer_id: str = Query(..., min_length=1),
    ) -> None:
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
        viewer_id: str = Query(..., min_length=1),
    ) -> PersonalContextConsent:
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
        viewer_id: str = Query(..., min_length=1),
    ) -> NoMatchPreference:
        """Let a participant opt out of future matching with one person."""
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
        viewer_id: str = Query(..., min_length=1),
    ) -> None:
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
        viewer_id: str = Query(..., min_length=1),
    ) -> list[NoMatchPreference]:
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            return repo.no_match_preferences(participant_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @api.post("/opportunities/preview", response_model=OpportunityPreview)
    def preview_opportunity(payload: OpportunityRequest) -> OpportunityPreview:
        return build_opportunity_preview(payload)

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
                for item in raw_signals
            ][:payload.limit]
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
        viewer_id: str = Query(..., min_length=1),
    ) -> PersonalContextPreview:
        """Preview viewer-owned context without persisting or broadcasting it."""
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
                for item in raw_signals
            ][:payload.limit]
            return build_personal_context_preview(viewer_id, payload.query, signals)
        except PersonalContextSourceError as error:
            raise HTTPException(status_code=502, detail="personal context source unavailable") from error
        except TimeoutError as error:
            raise HTTPException(status_code=502, detail="personal context source timed out") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=502, detail="personal context source returned invalid signals") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="personal context source unavailable") from error

    @api.post("/matches/preview", response_model=MatchPlan)
    def preview_match(payload: MatchRequest) -> MatchPlan:
        return build_match_plan(payload)

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
                for item in raw_candidates
            ][:payload.limit]
            request = MatchRequest(
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
        return build_match_plan(request)

    @api.post("/matches/confirm", response_model=MatchedTableResponse, status_code=status.HTTP_201_CREATED)
    def confirm_match(payload: ConfirmMatchRequest) -> MatchedTableResponse:
        plan = build_match_plan(payload)
        selected_ids = {seat.participant_id for seat in plan.selected}
        selected = [candidate for candidate in payload.candidates if candidate.participant_id in selected_ids]
        table_id = payload.table_id or uuid4().hex
        try:
            state = repo.create(table_id, payload.core_question, selected)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return MatchedTableResponse(plan=plan, state=projected(state))

    @api.get("/tables/{table_id}", response_model=TableState)
    def get_table(table_id: str, participant_id: str | None = Query(default=None)) -> TableState:
        return projected(table_or_404(table_id), participant_id)

    @api.post("/tables/{table_id}/participants", response_model=TableState)
    def add_participant(table_id: str, participant: ParticipantSeed) -> TableState:
        table_or_404(table_id)
        try:
            return projected(repo.add_participant(table_id, participant))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @api.post("/tables/{table_id}/participants/{participant_id}/leave", response_model=TableState)
    def leave_table(
        table_id: str,
        participant_id: str,
        viewer_id: str = Query(..., min_length=1),
    ) -> TableState:
        """Let a participant leave without deleting the table's prior history."""
        table_or_404(table_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            state = repo.remove_participant(table_id, participant_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return projected(state)

    @api.post("/tables/{table_id}/candidate-preview", response_model=TableCandidatePreview)
    async def preview_table_candidates(
        table_id: str,
        payload: CandidatePreviewRequest,
        participant_id: str = Query(..., min_length=1),
    ) -> TableCandidatePreview:
        """Recommend candidates for an open seat without mutating membership or invitations."""
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
        if candidate_source is None:
            raise HTTPException(status_code=503, detail="candidate source is not configured")
        try:
            raw_candidates = await asyncio.wait_for(
                candidate_source.search(
                    query=payload.query or state.core_question,
                    limit=payload.limit,
                ),
                timeout=candidate_source_timeout_seconds,
            )
            candidates = [
                item if isinstance(item, ParticipantSeed) else ParticipantSeed.model_validate(item)
                for item in raw_candidates
            ][:payload.limit]
            existing_invited = {
                item.candidate.participant_id for item in repo.invitations(table_id)
            }
            candidates = [
                item for item in candidates
                if item.participant_id not in existing_invited
                and not repo.is_no_match(participant_id, item.participant_id)
            ]
            recommendations = recommend_candidates(state, candidates, payload.limit)
        except CandidateSourceError as error:
            raise HTTPException(status_code=502, detail="candidate source unavailable") from error
        except TimeoutError as error:
            raise HTTPException(status_code=502, detail="candidate source timed out") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=502, detail="candidate source returned invalid candidates") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="candidate source unavailable") from error
        return TableCandidatePreview(
            table_id=table_id,
            core_question=state.core_question,
            open_seats=open_seats,
            role_gaps=infer_role_gaps(person.role for person in state.participants.values()),
            candidates=recommendations,
        )

    @api.post("/tables/{table_id}/comments", response_model=PeripheralComment)
    def add_peripheral_comment(
        table_id: str,
        payload: PeripheralCommentRequest,
        author_id: str = Query(..., min_length=1),
    ) -> PeripheralComment:
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
        return saved

    @api.get("/tables/{table_id}/comments", response_model=list[PeripheralComment])
    def get_peripheral_comments(table_id: str) -> list[PeripheralComment]:
        table_or_404(table_id)
        return repo.comments(table_id)

    @api.post(
        "/tables/{table_id}/comments/{comment_id}/promote",
        response_model=CommentPromotionResponse,
    )
    async def promote_peripheral_comment(
        table_id: str,
        comment_id: str = Path(..., min_length=1),
        participant_id: str = Query(..., min_length=1),
    ) -> CommentPromotionResponse:
        """Let a core member explicitly and safely bring one comment into the table."""
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
        reporter_id: str = Query(..., min_length=1),
    ) -> SafetyReport:
        """Collect a private member report for controlled moderation review."""
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
        reporter_id: str = Query(..., min_length=1),
    ) -> list[SafetyReport]:
        state = table_or_404(table_id)
        if reporter_id not in state.participants:
            raise HTTPException(status_code=403, detail="reporter must be a table participant")
        return repo.safety_reports(table_id, reporter_id)

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

    @api.post("/tables/{table_id}/invitations", response_model=InvitationView, status_code=status.HTTP_201_CREATED)
    def create_invitation(
        table_id: str,
        payload: CreateInvitationRequest,
        inviter_id: str = Query(..., min_length=1),
    ) -> InvitationView:
        table_or_404(table_id)
        try:
            invitation = repo.create_invitation(
                table_id, inviter_id, payload.candidate, payload.reason
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return invitation_view(invitation)

    @api.get("/tables/{table_id}/invitations", response_model=list[InvitationView])
    def get_invitations(
        table_id: str,
        participant_id: str = Query(..., min_length=1),
    ) -> list[InvitationView]:
        table_or_404(table_id)
        return [
            invitation_view(invitation)
            for invitation in repo.invitations(table_id)
            if invitation.candidate.participant_id == participant_id
        ]

    @api.post(
        "/tables/{table_id}/invitations/{invitation_id}/respond",
        response_model=InvitationResponse,
    )
    def respond_invitation(
        table_id: str,
        invitation_id: str,
        payload: RespondInvitationRequest,
        participant_id: str = Query(..., min_length=1),
    ) -> InvitationResponse:
        table_or_404(table_id)
        try:
            invitation, state = repo.respond_invitation(
                table_id, invitation_id, participant_id, payload.accept
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        projected_state = project_state_for_viewer(state, participant_id) if state is not None else None
        return InvitationResponse(
            invitation=invitation_view(invitation), state=projected_state
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
        participant_id: str = Query(..., min_length=1),
    ) -> SyncUpgradeDecision:
        return sync_decision(table_id, participant_id, signals)

    @api.post("/tables/{table_id}/sync/upgrade", response_model=SyncUpgradeResponse)
    def upgrade_to_sync(
        table_id: str,
        signals: SyncUpgradeSignals,
        participant_id: str = Query(..., min_length=1),
    ) -> SyncUpgradeResponse:
        decision = sync_decision(table_id, participant_id, signals)
        if not decision.eligible:
            raise HTTPException(status_code=409, detail=decision.model_dump(mode="json"))
        try:
            state = repo.upgrade_to_sync(table_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return SyncUpgradeResponse(decision=decision, state=projected(state, participant_id))

    @api.post("/tables/{table_id}/participants/{participant_id}/consent", response_model=TableState)
    def set_participant_consent(
        table_id: str,
        participant_id: str,
        payload: ParticipantConsentRequest,
        viewer_id: str = Query(..., min_length=1),
    ) -> TableState:
        table_or_404(table_id)
        if viewer_id != participant_id:
            raise HTTPException(status_code=403, detail="viewer_id must match participant_id")
        try:
            state = repo.set_profile_consent(table_id, participant_id, payload.profile_shared)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return projected(state, participant_id)

    @api.get("/tables/{table_id}/state", response_model=TableState)
    def get_state(table_id: str, participant_id: str | None = Query(default=None)) -> TableState:
        return projected(table_or_404(table_id), participant_id)

    @api.get("/tables/{table_id}/replay", response_model=ReplayResponse)
    def get_replay(
        table_id: str,
        from_version: int | None = Query(default=None, ge=0),
        participant_id: str | None = Query(default=None),
    ) -> ReplayResponse:
        table_or_404(table_id)
        try:
            snapshots = repo.replay(table_id, from_version)
            return ReplayResponse(
                table_id=table_id,
                messages=repo.turns(table_id),
                snapshots=[projected(item, participant_id) for item in snapshots],
                interventions=repo.interventions(table_id),
                comments=repo.comments(table_id),
                comment_promotions=repo.comment_promotions(table_id),
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @api.get("/tables/{table_id}/interventions", response_model=list[InterventionRecord])
    def get_interventions(table_id: str) -> list[InterventionRecord]:
        table_or_404(table_id)
        return repo.interventions(table_id)

    def close_follow_ups(table_id: str, participant_id: str) -> tuple[TableState, list[FollowUpItem], dict[int, FollowUpOutcome]]:
        state = table_or_404(table_id)
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        if participant_id not in state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {participant_id}")
        try:
            baseline = build_shared_baseline(state, turns=repo.turns(table_id))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        outcomes = {item.follow_up_index: item for item in repo.follow_up_outcomes(table_id)}
        return state, baseline.collective_next_steps, outcomes

    @api.get("/tables/{table_id}/follow-ups", response_model=list[FollowUpStatusResponse])
    def get_follow_ups(
        table_id: str,
        participant_id: str = Query(..., min_length=1),
    ) -> list[FollowUpStatusResponse]:
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
        follow_up_index: int = Path(..., ge=0),
        payload: FollowUpOutcomeRequest = ...,
        participant_id: str = Query(..., min_length=1),
    ) -> FollowUpStatusResponse:
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

    @api.post("/tables/{table_id}/feedback", response_model=ValueFeedback)
    def submit_value_feedback(
        table_id: str,
        payload: ValueFeedbackRequest,
        participant_id: str = Query(..., min_length=1),
    ) -> ValueFeedback:
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
        participant_id: str = Query(..., min_length=1),
    ) -> FeedbackSummary:
        return feedback_summary(table_id, participant_id)

    @api.post("/tables/{table_id}/soft-expire", response_model=TableState)
    def soft_expire_table(
        table_id: str,
        payload: SoftExpireRequest,
        participant_id: str = Query(..., min_length=1),
    ) -> TableState:
        """Hide a stale table from discovery while preserving its history and close path."""
        state = table_or_404(table_id)
        if participant_id not in state.participants:
            raise HTTPException(status_code=403, detail="participant_id must be a table participant")
        try:
            expired = repo.soft_expire_table(table_id, payload.reason)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return projected(expired, participant_id)

    @api.post("/tables/{table_id}/close", response_model=SharedBaseline)
    def close_table(table_id: str) -> SharedBaseline:
        state = table_or_404(table_id)
        try:
            build_shared_baseline(state, turns=repo.turns(table_id))
            closed = repo.close_table(table_id)
            return build_shared_baseline(closed, turns=repo.turns(table_id))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @api.post(
        "/tables/{table_id}/recompose",
        response_model=RecomposeTableResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def recompose_table(
        table_id: str,
        payload: RecomposeTableRequest,
    ) -> RecomposeTableResponse:
        """Create a new table from a closed table's evolved question and chosen seeds."""
        state = table_or_404(table_id)
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        try:
            baseline = build_shared_baseline(state, turns=repo.turns(table_id))
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
        participant_id: str = Query(..., min_length=1),
    ) -> CloseArtifactsResponse:
        """Rebuild the evidence-backed close card after reconnect/restart."""
        state = table_or_404(table_id)
        if not state.conversation.closed:
            raise HTTPException(status_code=409, detail="table is not closed")
        if participant_id not in state.participants:
            raise HTTPException(status_code=404, detail=f"unknown participant: {participant_id}")
        try:
            baseline = build_shared_baseline(state, turns=repo.turns(table_id))
            personal = build_personal_card(state, participant_id)
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
