import json
import sys

from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.cli.seed_demo import main
from app.demo.bootstrap import seed_demo_tables


def test_seed_demo_tables_is_idempotent_and_keeps_three_open_tables() -> None:
    repository = InMemoryTableRepository()

    first = seed_demo_tables(repository)
    second = seed_demo_tables(repository)

    assert [item.table_id for item in first] == ["demo-agent", "demo-rest", "demo-gap"]
    assert [item.status for item in first] == ["created", "created", "created"]
    assert [item.participant_count for item in first] == [4, 4, 2]
    assert [item.status for item in second] == ["existing", "existing", "existing"]
    assert [item.state_version for item in second] == [0, 0, 0]
    assert [state.table_id for state in repository.list_tables()] == [
        "demo-agent",
        "demo-rest",
        "demo-gap",
    ]


def test_seed_demo_tables_survives_json_restart_without_overwriting_state(tmp_path) -> None:
    path = tmp_path / "runtime" / "tables.json"
    repository = JsonTableRepository(path)
    seed_demo_tables(repository)
    repository.append_message_once(
        "demo-agent",
        "architect",
        "先把技术验收标准说清楚。",
        "demo-message-1",
    )

    restarted = JsonTableRepository(path)
    results = seed_demo_tables(restarted)

    assert [item.status for item in results] == ["existing", "existing", "existing"]
    assert restarted.get("demo-agent").version == 1
    assert restarted.turns("demo-agent")[0].message_id == "demo-message-1"


def test_seed_demo_cli_uses_repository_path_and_emits_machine_readable_summary(
    tmp_path, monkeypatch, capsys
) -> None:
    path = tmp_path / "cli" / "tables.json"
    monkeypatch.setattr(sys, "argv", ["seed_demo", "--path", str(path)])

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == str(path)
    assert [item["table_id"] for item in payload["tables"]] == [
        "demo-agent",
        "demo-rest",
        "demo-gap",
    ]
    assert path.exists()
