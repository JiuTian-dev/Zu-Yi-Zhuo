"""Minimal REST API for one explainable conversation table."""

import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain import HumanTurn, InvitationView, InterventionRecord, MatchPlan, MatchRequest, ParticipantSeed, PersonalCard, SharedBaseline, SyncUpgradeDecision, SyncUpgradeSignals, TableState
from app.matching import build_match_plan
from app.orchestrator import build_personal_card, build_shared_baseline, evaluate_sync_upgrade
from app.providers import LLMProvider

from .repository import InMemoryTableRepository
from .privacy import project_state_for_viewer
from .websocket import register_websocket_routes
from app.sources import CandidateSource, CandidateSourceError


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


def create_app(
    repository: InMemoryTableRepository | None = None,
    provider: LLMProvider | None = None,
    candidate_source: CandidateSource | None = None,
) -> FastAPI:
    """Create an app with an injectable repository for tests and future persistence."""
    repo = repository or InMemoryTableRepository()
    api = FastAPI(title="组一桌 Conversation Orchestrator")
    api.state.repository = repo
    api.state.provider = provider
    api.state.candidate_source = candidate_source
    raw_origins = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
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

    @api.post("/matches/preview", response_model=MatchPlan)
    def preview_match(payload: MatchRequest) -> MatchPlan:
        return build_match_plan(payload)

    @api.post("/matches/source-preview", response_model=MatchPlan)
    async def preview_source_match(payload: SourceMatchRequest) -> MatchPlan:
        """Run an injected, authorized source through the same match preview."""
        if candidate_source is None:
            raise HTTPException(status_code=503, detail="candidate source is not configured")
        try:
            raw_candidates = await candidate_source.search(
                query=payload.query or payload.core_question,
                limit=payload.limit,
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
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @api.get("/tables/{table_id}/interventions", response_model=list[InterventionRecord])
    def get_interventions(table_id: str) -> list[InterventionRecord]:
        table_or_404(table_id)
        return repo.interventions(table_id)

    @api.post("/tables/{table_id}/close", response_model=SharedBaseline)
    def close_table(table_id: str) -> SharedBaseline:
        state = table_or_404(table_id)
        try:
            build_shared_baseline(state, turns=repo.turns(table_id))
            closed = repo.close_table(table_id)
            return build_shared_baseline(closed, turns=repo.turns(table_id))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
