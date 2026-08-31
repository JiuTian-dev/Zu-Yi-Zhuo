"""Minimal REST API for one explainable conversation table."""

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.domain import HumanTurn, ParticipantSeed, SharedBaseline, TableState
from app.orchestrator import build_shared_baseline

from .repository import InMemoryTableRepository
from .privacy import project_state_for_viewer
from .websocket import register_websocket_routes


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


def create_app(repository: InMemoryTableRepository | None = None) -> FastAPI:
    """Create an app with an injectable repository for tests and future persistence."""
    repo = repository or InMemoryTableRepository()
    api = FastAPI(title="组一桌 Conversation Orchestrator")
    api.state.repository = repo
    register_websocket_routes(api, repo)

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

    @api.post("/tables/{table_id}/participants/{participant_id}/consent", response_model=TableState)
    def set_participant_consent(
        table_id: str, participant_id: str, payload: ParticipantConsentRequest
    ) -> TableState:
        table_or_404(table_id)
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

    @api.post("/tables/{table_id}/close", response_model=SharedBaseline)
    def close_table(table_id: str) -> SharedBaseline:
        state = table_or_404(table_id)
        try:
            return build_shared_baseline(state, turns=repo.turns(table_id))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return api


app = create_app()
