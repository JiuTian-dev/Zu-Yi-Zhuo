"""Small, opt-in public surface for a repeatable judge experience."""

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.identity import require_request_identity
from app.api.privacy import project_state_for_viewer
from app.demo.service import JudgeDemoService


class CreateDemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="我", min_length=1, max_length=60)
    request_id: str = Field(min_length=1, max_length=120)

    @field_validator("participant_id", "display_name", "request_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


def register_demo_routes(api, service: JudgeDemoService, identity_resolver) -> None:
    def require_available() -> None:
        if not service.enabled:
            raise HTTPException(status_code=404, detail="模拟体验未开启")
        if not service.available:
            raise HTTPException(status_code=503, detail="模拟体验暂不可用，请先配置后端模型")

    @api.get("/demo/cases/ai_friendship")
    def get_case() -> dict:
        if not service.enabled:
            raise HTTPException(status_code=404, detail="模拟体验未开启")
        return service.public_case()

    @api.post("/demo/sessions")
    async def create_session(payload: CreateDemoRequest, request: Request, response: Response) -> dict:
        require_available()
        require_request_identity(identity_resolver, request, payload.participant_id)
        try:
            state, created = await service.create(payload.participant_id, payload.display_name, payload.request_id)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        response.status_code = 201 if created else 200
        return {"table_id": state.table_id, "state": project_state_for_viewer(state, payload.participant_id).model_dump(mode="json")}

    @api.post("/demo/sessions/{table_id}/resume")
    async def resume_session(table_id: str, request: Request, participant_id: str = Query(..., min_length=1)) -> dict:
        require_available()
        require_request_identity(identity_resolver, request, participant_id)
        try:
            state = await service.resume(table_id, participant_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="这桌不存在") from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"table_id": state.table_id, "state": project_state_for_viewer(state, participant_id).model_dump(mode="json")}
