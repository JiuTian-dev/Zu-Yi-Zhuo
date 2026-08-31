import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed, PeripheralComment


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="桌内立场",
    )


def _client(table_id: str = "comment-table") -> tuple[TestClient, InMemoryTableRepository]:
    repository = InMemoryTableRepository()
    repository.create(table_id, "如何让讨论产生行动？", [_seed("p1"), _seed("p2")])
    return TestClient(create_app(repository)), repository


def _payload(comment_id: str = "c1", text: str = "可以补充一个真实案例") -> dict[str, str]:
    return {"comment_id": comment_id, "display_name": "旁听者", "text": text}


def test_rest_peripheral_comments_are_public_and_idempotent() -> None:
    client, repository = _client()

    first = client.post(
        "/tables/comment-table/comments?author_id=guest", json=_payload()
    )
    duplicate = client.post(
        "/tables/comment-table/comments?author_id=guest", json=_payload()
    )
    conflict = client.post(
        "/tables/comment-table/comments?author_id=guest",
        json=_payload(text="改写同一个评论"),
    )

    assert first.status_code == duplicate.status_code == 200
    assert first.json() == duplicate.json()
    assert conflict.status_code == 409
    assert client.get("/tables/comment-table/comments").json() == [first.json()]
    assert repository.turns("comment-table") == []
    assert repository.get("comment-table").version == 0


def test_commenter_websocket_can_write_comments_but_not_core_turns() -> None:
    client, repository = _client("comment-ws")

    with client.websocket_connect(
        "/ws/tables/comment-ws?participant_id=guest&viewer_mode=observer"
    ) as observer:
        assert observer.receive_json()["type"] == "table_state_changed"
        with client.websocket_connect(
            "/ws/tables/comment-ws?participant_id=guest&viewer_mode=commenter"
        ) as commenter:
            assert commenter.receive_json()["type"] == "table_state_changed"
            commenter.send_json({
                "type": "peripheral_comment",
                "comment_id": "ws-c1",
                "author_id": "guest",
                "display_name": "旁听者",
                "text": "这个问题也许需要看真实采购流程",
            })
            observer_event = observer.receive_json()
            commenter_event = commenter.receive_json()
            assert observer_event == commenter_event
            assert observer_event["type"] == "peripheral_comment"
            assert observer_event["comment"]["state_version"] == 0

            commenter.send_json({
                "type": "human_message",
                "message_id": "not-a-core-turn",
                "participant_id": "guest",
                "text": "不应进入核心桌",
                "client_ts": 1,
            })
            assert commenter.receive_json() == {
                "type": "error",
                "code": "commenter_read_only",
                "detail": "commenter connections can only submit peripheral comments",
            }

    assert len(repository.comments("comment-ws")) == 1
    assert repository.turns("comment-ws") == []
    assert set(repository.get("comment-ws").participants) == {"p1", "p2"}


def test_commenter_identity_and_lifecycle_boundaries() -> None:
    client, repository = _client("comment-guards")
    assert client.post(
        "/tables/comment-guards/comments?author_id=guest", json=_payload()
    ).status_code == 200
    assert client.post(
        "/tables/comment-guards/comments?author_id=guest", json=_payload()
    ).status_code == 200

    with client.websocket_connect(
        "/ws/tables/comment-guards?participant_id=guest&viewer_mode=commenter"
    ) as commenter:
        assert commenter.receive_json()["type"] == "table_state_changed"
        commenter.send_json({
            "type": "peripheral_comment",
            "comment_id": "ws-conflict",
            "author_id": "other",
            "display_name": "冒用",
            "text": "不应通过",
        })
        assert commenter.receive_json()["code"] == "invalid_event"

    repository.close_table("comment-guards")
    assert client.post(
        "/tables/comment-guards/comments?author_id=guest", json=_payload("closed")
    ).status_code == 409
    assert client.get("/tables/comment-guards/comments").status_code == 200


def test_json_repository_persists_comments_and_accepts_legacy_tables(tmp_path) -> None:
    path = tmp_path / "tables.json"
    repository = JsonTableRepository(path)
    repository.create("persist-comments", "Q", [_seed("p1")])
    saved, created = repository.append_comment_once(
        PeripheralComment(
            comment_id="c1",
            table_id="persist-comments",
            author_id="guest",
            display_name="旁听者",
            text="保留公共补充",
            state_version=0,
        )
    )
    assert created
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["tables"]["persist-comments"]["comments"][0]["comment_id"] == "c1"

    reloaded = JsonTableRepository(path)
    assert reloaded.comments("persist-comments") == [saved]

    payload["tables"]["persist-comments"].pop("comments")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    legacy = JsonTableRepository(path)
    assert legacy.comments("persist-comments") == []
