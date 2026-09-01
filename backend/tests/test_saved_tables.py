import json

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import (
    MAX_SAVED_TABLES_PER_PARTICIPANT,
    InMemoryTableRepository,
    JsonTableRepository,
)
from app.domain import ParticipantSeed


def _seed(participant_id: str, role: str = "讨论参与者") -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="公开立场",
    )


def _identity(request) -> str | None:
    return request.headers.get("x-user-id")


def test_saved_table_is_private_idempotent_and_does_not_mutate_or_train() -> None:
    repository = InMemoryTableRepository()
    repository.create("table-a", "一个值得稍后回来的问题", [_seed("member")])
    client = TestClient(create_app(repository))

    first = client.put(
        "/participants/viewer/saved-tables/table-a?viewer_id=viewer"
    )
    retry = client.put(
        "/participants/viewer/saved-tables/table-a?viewer_id=viewer"
    )
    own = client.get(
        "/participants/viewer/saved-tables?viewer_id=viewer"
    )
    other = client.get(
        "/participants/other/saved-tables?viewer_id=other"
    )

    assert first.status_code == 200
    assert retry.json() == first.json()
    assert first.json()["table_id"] == "table-a"
    assert first.json()["lobby"]["core_question"] == "一个值得稍后回来的问题"
    assert own.json()["total"] == 1
    assert [item["table_id"] for item in own.json()["items"]] == ["table-a"]
    assert other.json()["items"] == []
    assert repository.get("table-a").version == 0
    assert repository.behavior_events("viewer") == []
    assert "saved_count" not in first.text


def test_saved_tables_are_newest_first_paginated_and_keep_inactive_tables() -> None:
    repository = InMemoryTableRepository()
    repository.create("closed", "已经结束但仍值得回看", [_seed("closed-member")])
    repository.close_table("closed")
    repository.create("soft", "暂时停下的桌", [_seed("soft-member")])
    repository.soft_expire_table("soft", "暂时没有新参与")
    repository.create("full", "已经坐满的桌", [_seed(f"full-{index}") for index in range(5)])
    client = TestClient(create_app(repository))
    for table_id in ("closed", "soft", "full"):
        response = client.put(
            f"/participants/viewer/saved-tables/{table_id}?viewer_id=viewer"
        )
        assert response.status_code == 200

    first_page = client.get(
        "/participants/viewer/saved-tables?viewer_id=viewer&offset=0&limit=2"
    ).json()
    second_page = client.get(
        "/participants/viewer/saved-tables?viewer_id=viewer&offset=2&limit=2"
    ).json()

    assert first_page["total"] == 3
    assert [item["table_id"] for item in first_page["items"]] == ["full", "soft"]
    assert [item["lobby"]["status"] for item in first_page["items"]] == [
        "open", "soft_expired",
    ]
    assert [item["table_id"] for item in second_page["items"]] == ["closed"]
    assert second_page["items"][0]["lobby"]["status"] == "closed"


def test_remove_saved_table_is_idempotent_and_keeps_the_table() -> None:
    repository = InMemoryTableRepository()
    repository.create("table-a", "Q", [_seed("member")])
    client = TestClient(create_app(repository))
    client.put("/participants/viewer/saved-tables/table-a?viewer_id=viewer")

    first = client.delete(
        "/participants/viewer/saved-tables/table-a?viewer_id=viewer"
    )
    retry = client.delete(
        "/participants/viewer/saved-tables/table-a?viewer_id=viewer"
    )

    assert first.status_code == 204
    assert retry.status_code == 204
    assert repository.saved_table_ids("viewer") == []
    assert repository.get("table-a").core_question == "Q"


def test_saved_table_capacity_is_bounded() -> None:
    repository = InMemoryTableRepository()
    for index in range(MAX_SAVED_TABLES_PER_PARTICIPANT + 1):
        table_id = f"table-{index:03d}"
        repository.create(table_id, f"Q{index}", [_seed(f"member-{index}")])
        if index < MAX_SAVED_TABLES_PER_PARTICIPANT:
            assert repository.save_table("viewer", table_id) is True

    client = TestClient(create_app(repository))
    response = client.put(
        f"/participants/viewer/saved-tables/table-{MAX_SAVED_TABLES_PER_PARTICIPANT:03d}"
        "?viewer_id=viewer"
    )

    assert response.status_code == 409
    assert "cannot exceed" in response.json()["detail"]
    assert len(repository.saved_table_ids("viewer")) == MAX_SAVED_TABLES_PER_PARTICIPANT


def test_saved_tables_persist_and_legacy_snapshots_default_empty(tmp_path) -> None:
    path = tmp_path / "saved-tables.json"
    repository = JsonTableRepository(path)
    repository.create("first", "第一桌", [_seed("first-member")])
    repository.create("second", "第二桌", [_seed("second-member")])
    repository.save_table("viewer", "first")
    repository.save_table("viewer", "second")

    restarted = JsonTableRepository(path)
    assert restarted.saved_table_ids("viewer") == ["second", "first"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["saved_tables"] == {"viewer": ["first", "second"]}

    payload.pop("saved_tables")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert JsonTableRepository(path).saved_table_ids("viewer") == []


def test_malformed_saved_tables_fail_closed_on_json_load(tmp_path) -> None:
    path = tmp_path / "malformed-saved-tables.json"
    repository = JsonTableRepository(path)
    repository.create("known", "Q", [_seed("member")])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["saved_tables"] = {"viewer": ["missing"]}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid saved tables"):
        JsonTableRepository(path)


def test_saved_table_routes_require_self_identity_and_known_table() -> None:
    repository = InMemoryTableRepository()
    repository.create("known", "Q", [_seed("member")])
    client = TestClient(create_app(repository, identity_resolver=_identity))

    assert client.put(
        "/participants/viewer/saved-tables/known?viewer_id=viewer"
    ).status_code == 401
    assert client.put(
        "/participants/viewer/saved-tables/known?viewer_id=viewer",
        headers={"X-User-ID": "other"},
    ).status_code == 403
    assert client.put(
        "/participants/viewer/saved-tables/missing?viewer_id=viewer",
        headers={"X-User-ID": "viewer"},
    ).status_code == 404
    valid = client.put(
        "/participants/viewer/saved-tables/known?viewer_id=viewer",
        headers={"X-User-ID": "viewer"},
    )
    assert valid.status_code == 200
    assert client.get(
        "/participants/viewer/saved-tables?viewer_id=other",
        headers={"X-User-ID": "other"},
    ).status_code == 403
    assert client.get(
        "/participants/viewer/saved-tables?viewer_id=viewer&limit=101",
        headers={"X-User-ID": "viewer"},
    ).status_code == 422
