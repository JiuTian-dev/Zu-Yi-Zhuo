import json
import sys

from app.cli.journey_demo import main
from app.demo.journey import JOURNEY_CORE_QUESTION, run_journey_demo


def test_journey_demo_report_covers_real_api_boundaries() -> None:
    report = run_journey_demo()

    assert report["core_question"] == JOURNEY_CORE_QUESTION
    assert all(report["steps"].values())
    assert report["opportunity"]["signal_ids"]
    assert report["opportunity"]["candidate_ids"]
    assert len(report["match"]["selected"]) == 4
    assert report["turn"]["agent_action"]["action"] == "PASS"
    assert report["turn"]["agent_action"]["target_participant_id"] == "public-buyer"
    assert report["close_artifacts"]["personal_card"]["participant_id"] == "public-architect"
    assert report["evaluation"]["human_turn_count"] == 1
    assert report["evaluation"]["intervention_count"] == 1
    assert report["replay_summary"] == {
        "message_count": 1,
        "snapshot_count": 4,
        "intervention_count": 1,
        "source_signal_count": 4,
        "closed": True,
    }
    # The report only contains the actor's own reflection card; no other
    # participant's private profile fields are copied into the output.
    serialized = json.dumps(report, ensure_ascii=False)
    assert "declared_position" not in serialized
    assert "unused_relevant_experience" not in serialized


def test_journey_demo_cli_is_repeatable_and_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["journey_demo"])

    main()
    first = json.loads(capsys.readouterr().out)
    main()
    second = json.loads(capsys.readouterr().out)

    assert first == second
    assert first["steps"]["table_closed"] is True
