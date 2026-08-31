import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.domain import ParticipantSeed


class _Source:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = []

    async def search(self, *, query, limit):
        self.calls.append((query, limit))
        return self.candidates[:limit]


class _FailingSource:
    async def search(self, *, query, limit):
        raise RuntimeError("upstream unavailable")


def _candidate(participant_id: str, role: str) -> dict:
    return {
        "participant_id": participant_id,
        "display_name": participant_id,
        "role": role,
        "declared_position": "私有立场",
        "relevant_experience": [{"text": "私有经历", "source_ref": "authorized:answer"}],
    }


def test_source_preview_normalizes_candidates_and_reuses_public_match_contract() -> None:
    source = _Source([_candidate("p1", "研究员"), _candidate("p2", "采购负责人")])
    client = TestClient(create_app(candidate_source=source))

    response = client.post("/matches/source-preview", json={
        "core_question": "采购如何落地 AI？", "query": "采购 AI", "table_size": 2, "limit": 2,
    })

    assert response.status_code == 200
    payload = response.json()
    assert {seat["participant_id"] for seat in payload["selected"]} == {"p1", "p2"}
    assert all("私有" not in reason["reason"] for reason in payload["reasons"])
    assert source.calls == [("采购 AI", 2)]


def test_source_preview_is_explicitly_unavailable_without_an_adapter() -> None:
    response = TestClient(create_app()).post(
        "/matches/source-preview", json={"core_question": "Q", "table_size": 2}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "candidate source is not configured"}


def test_source_preview_fails_closed_on_invalid_source_output() -> None:
    source = _Source([ParticipantSeed.model_validate(_candidate("p1", "研究员"))])
    response = TestClient(create_app(candidate_source=source)).post(
        "/matches/source-preview", json={"core_question": "Q", "table_size": 2}
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "candidate source returned invalid candidates"}


def test_source_preview_hides_upstream_failure_details() -> None:
    response = TestClient(create_app(candidate_source=_FailingSource())).post(
        "/matches/source-preview", json={"core_question": "Q", "table_size": 2}
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "candidate source unavailable"}
