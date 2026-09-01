from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import HumanTurn, ParticipantSeed
from app.matching import evaluate_recruitment_need
from app.orchestrator import enforce_safety, evaluate_safety


class _Source:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, *, query: str, limit: int):
        self.calls.append((query, limit))
        return [{
            "participant_id": "candidate",
            "display_name": "候选实践者",
            "role": "实践者",
            "declared_position": "愿意补充公开实践",
        }]


def _seed(participant_id: str, role: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="公开立场",
    )


def _four(*, covers_practice: bool = False) -> list[ParticipantSeed]:
    return [
        _seed("p1", "产品负责人"),
        _seed("p2", "研究员"),
        _seed("p3", "运营实践者" if covers_practice else "圆桌主持人"),
        _seed("p4", "行业观察者"),
    ]


def _add_live_gap(repository: InMemoryTableRepository, table_id: str) -> None:
    repository.append_turn(
        table_id,
        HumanTurn(turn_id=1, participant_id="p1", text="技术模型已经可以上线。"),
    )
    repository.append_turn(
        table_id,
        HumanTurn(turn_id=2, participant_id="p2", text="采购预算和责任链才是落地瓶颈。"),
    )


def _header_identity(request) -> str | None:
    return request.headers.get("x-user-id")


def test_recruitment_uses_seat_baseline_then_waits_for_real_discussion() -> None:
    repository = InMemoryTableRepository()
    repository.create("small", "AI 采购如何落地？", _four()[:3])
    below_minimum = evaluate_recruitment_need(repository.get("small"), repository.turns("small"))

    repository.create("ready", "AI 采购如何落地？", _four())
    waiting = evaluate_recruitment_need(repository.get("ready"), repository.turns("ready"))

    assert below_minimum.should_recruit is True
    assert below_minimum.trigger == "below_minimum"
    assert below_minimum.evidence_turns == []
    assert below_minimum.suggested_query == "AI 采购如何落地？ 实践者"
    assert waiting.should_recruit is False
    assert waiting.trigger == "wait_for_discussion"
    assert waiting.evidence_turns == []


def test_live_multi_speaker_gap_drives_member_decision_and_candidate_query() -> None:
    repository = InMemoryTableRepository()
    repository.create("live-gap", "AI 采购如何真正落地？", _four())
    _add_live_gap(repository, "live-gap")
    source = _Source()
    client = TestClient(create_app(repository, candidate_source=source))

    decision_response = client.get("/tables/live-gap/recruitment?participant_id=p1")
    preview_response = client.post(
        "/tables/live-gap/candidate-preview?participant_id=p1",
        json={"limit": 1},
    )

    assert decision_response.status_code == 200
    decision = decision_response.json()
    assert decision == preview_response.json()["recruitment"]
    assert decision["should_recruit"] is True
    assert decision["trigger"] == "live_role_gap"
    assert decision["role_gaps"] == ["实践者"]
    assert decision["evidence_turns"] == [1, 2]
    assert decision["suggested_query"] == "采购决策链如何影响技术进入企业？ 实践者"
    assert "技术模型已经可以上线" not in decision_response.text
    assert "采购预算和责任链" not in decision_response.text
    assert "p1" not in decision_response.text and "p2" not in decision_response.text
    assert source.calls == [("采购决策链如何影响技术进入企业？ 实践者", 1)]
    assert repository.get("live-gap").version == 2
    assert repository.invitations("live-gap") == []


def test_recruitment_endpoint_is_member_and_identity_scoped_without_candidate_source() -> None:
    repository = InMemoryTableRepository()
    repository.create("protected", "Q", _four())
    client = TestClient(create_app(repository, identity_resolver=_header_identity))

    assert client.get("/tables/protected/recruitment?participant_id=p1").status_code == 401
    assert client.get(
        "/tables/protected/recruitment?participant_id=p1",
        headers={"X-User-ID": "p2"},
    ).status_code == 403
    assert client.get(
        "/tables/protected/recruitment?participant_id=ghost",
        headers={"X-User-ID": "ghost"},
    ).status_code == 403
    valid = client.get(
        "/tables/protected/recruitment?participant_id=p1",
        headers={"X-User-ID": "p1"},
    )
    assert valid.status_code == 200
    assert valid.json()["trigger"] == "wait_for_discussion"


def test_complete_information_roles_do_not_turn_live_disagreement_into_recruitment() -> None:
    repository = InMemoryTableRepository()
    repository.create("complete", "AI 采购如何落地？", _four(covers_practice=True))
    _add_live_gap(repository, "complete")

    decision = evaluate_recruitment_need(
        repository.get("complete"), repository.turns("complete")
    )

    assert decision.should_recruit is False
    assert decision.trigger == "composition_sufficient"
    assert decision.role_gaps == []
    assert decision.evidence_turns == [1, 2]
    assert decision.suggested_query is None


def test_recruitment_stops_for_full_unavailable_and_critical_tables() -> None:
    repository = InMemoryTableRepository()
    repository.create("full", "Q", [*_four(), _seed("p5", "业务实践者")])
    full = evaluate_recruitment_need(repository.get("full"), repository.turns("full"))

    repository.create("closed", "Q", _four())
    repository.close_table("closed")
    closed = evaluate_recruitment_need(repository.get("closed"), repository.turns("closed"))

    repository.create("expired", "Q", _four())
    repository.soft_expire_table("expired", "问题热度下降")
    expired = evaluate_recruitment_need(repository.get("expired"), repository.turns("expired"))

    repository.create("paused", "Q", _four())
    unsafe = evaluate_safety("我会威胁你。", 1)
    repository.append_safety_state("paused", enforce_safety(repository.get("paused"), unsafe))
    paused = evaluate_recruitment_need(repository.get("paused"), repository.turns("paused"))

    assert (full.should_recruit, full.trigger, full.open_seats) == (False, "table_full", 0)
    assert (closed.should_recruit, closed.trigger) == (False, "table_unavailable")
    assert (expired.should_recruit, expired.trigger) == (False, "table_unavailable")
    assert (paused.should_recruit, paused.trigger) == (False, "safety_paused")


def test_recruitment_decision_survives_json_restart(tmp_path) -> None:
    path = tmp_path / "recruitment.json"
    repository = JsonTableRepository(path)
    repository.create("durable", "AI 采购如何落地？", _four())
    _add_live_gap(repository, "durable")
    before = evaluate_recruitment_need(repository.get("durable"), repository.turns("durable"))

    restored = JsonTableRepository(path)
    response = TestClient(create_app(restored)).get(
        "/tables/durable/recruitment?participant_id=p1"
    )

    assert response.status_code == 200
    assert response.json() == before.model_dump(exclude_none=True)
    assert response.json()["evidence_turns"] == [1, 2]
