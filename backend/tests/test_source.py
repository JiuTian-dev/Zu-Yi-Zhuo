import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.domain import ParticipantSeed
from app.sources import CandidateSourceError, CommandCandidateSource


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


class _HangingSource:
    async def search(self, *, query, limit):
        await asyncio.sleep(0.2)
        return []


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


def test_source_preview_times_out_without_leaking_adapter_details() -> None:
    response = TestClient(create_app(
        candidate_source=_HangingSource(), candidate_source_timeout_seconds=0.01,
    )).post("/matches/source-preview", json={"core_question": "Q", "table_size": 2})
    assert response.status_code == 502
    assert response.json() == {"detail": "candidate source timed out"}


def test_source_preview_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="positive"):
        create_app(candidate_source_timeout_seconds=0)


def test_command_candidate_source_uses_bounded_json_stdin_stdout_contract() -> None:
    script = (
        "import json,sys; request=json.load(sys.stdin); "
        "print(json.dumps({'candidates':[{'participant_id':'p1','display_name':'甲',"
        "'role':'研究员','declared_position':'立场',"
        "'relevant_experience':[{'text':'经历','source_ref':'source:1'}]}]}))"
    )
    source = CommandCandidateSource([sys.executable, "-c", script])

    candidates = asyncio.run(source.search(query="采购;不要执行", limit=2))

    assert len(candidates) == 1
    assert candidates[0].participant_id == "p1"


def test_command_candidate_source_fails_closed_on_invalid_or_unsuccessful_command() -> None:
    invalid = CommandCandidateSource([
        sys.executable, "-c", "print('not-json')",
    ])
    with pytest.raises(CandidateSourceError, match="invalid JSON"):
        asyncio.run(invalid.search(query="Q", limit=2))

    failed = CommandCandidateSource([
        sys.executable, "-c", "raise SystemExit(3)",
    ])
    with pytest.raises(CandidateSourceError, match="unsuccessfully"):
        asyncio.run(failed.search(query="Q", limit=2))


def test_command_candidate_source_enforces_output_and_process_time_limits() -> None:
    oversized = CommandCandidateSource(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100)"],
        max_output_bytes=16,
    )
    with pytest.raises(CandidateSourceError, match="too large"):
        asyncio.run(oversized.search(query="Q", limit=2))

    hanging = CommandCandidateSource(
        [sys.executable, "-c", "import time; time.sleep(0.2)"],
        timeout_seconds=0.01,
    )
    with pytest.raises(CandidateSourceError, match="timed out"):
        asyncio.run(hanging.search(query="Q", limit=2))


def test_runtime_candidate_source_command_is_configured_as_json_argv(monkeypatch) -> None:
    command = [sys.executable, "-c", "import sys; sys.stdout.write('{\"candidates\":[]}')"]
    monkeypatch.setenv("CANDIDATE_SOURCE_COMMAND", json.dumps(command))

    from app.main import _build_candidate_source

    source = _build_candidate_source()
    assert isinstance(source, CommandCandidateSource)
    assert tuple(command) == source.command


def test_runtime_candidate_source_command_rejects_malformed_configuration(monkeypatch) -> None:
    monkeypatch.setenv("CANDIDATE_SOURCE_COMMAND", "not-json")

    from app.main import _build_candidate_source

    with pytest.raises(RuntimeError, match="JSON string array"):
        _build_candidate_source()
