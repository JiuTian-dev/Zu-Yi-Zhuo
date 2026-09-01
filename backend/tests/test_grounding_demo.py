import json
import sys

from app.cli.grounding_demo import main
from app.demo.grounding import run_grounding_demo


def test_grounding_demo_proves_real_source_to_replay_path() -> None:
    report = run_grounding_demo()

    assert all(report["steps"].values())
    assert report["fact_conflict"] == {
        "evidence_turns": [1, 2],
        "participant_ids": ["p1", "p2"],
    }
    assert report["grounding"] == {
        "action": "GROUND",
        "state_version": 3,
        "signal_id": "grounding-demo-signal",
        "source_ref": "demo:public:grounding",
    }
    assert report["replay"] == {
        "message_count": 2,
        "intervention_count": 1,
        "grounding_signal_ids": ["grounding-demo-signal"],
    }


def test_grounding_demo_cli_is_repeatable_and_prints_only_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["grounding_demo"])

    main()
    first = json.loads(capsys.readouterr().out)
    main()
    second = json.loads(capsys.readouterr().out)

    assert first == second
    assert first["steps"]["ground_action_broadcast"] is True
