import json
import sys

from app.cli.intent_demo import main
from app.demo.intent import run_intent_demo


def test_intent_demo_is_deterministic_and_reports_only_public_summary() -> None:
    first = run_intent_demo()
    second = run_intent_demo()

    assert first == second
    assert first["session"] == {
        "initial_status": "clarifying",
        "final_status": "ready",
        "route": "new_table",
        "turn_count": 2,
    }
    assert first["candidate_source_query"] == "城市徒步路线和装备选择"
    assert first["selected_participant_ids"] == [
        "intent-beginner",
        "intent-bridge",
        "intent-practitioner",
        "intent-professional",
    ]
    assert first["table_id"] == "intent-demo-table"
    assert first["participant_count"] == 4
    serialized = json.dumps(first, ensure_ascii=False)
    assert "preview_token" not in serialized
    assert "declared_position" not in serialized
    assert "私有" not in serialized


def test_intent_demo_cli_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["intent_demo"])
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["session"]["route"] == "new_table"
    assert payload["participant_count"] == 4
