from pathlib import Path

from app.evaluation.multi_agent_baseline import load_fixtures, run_baseline


FIXTURES = Path(__file__).parent / "fixtures" / "multi_agent" / "manifest.json"


def test_baseline_manifest_is_complete_and_replayable() -> None:
    assert len(load_fixtures(FIXTURES)) == 12
    runs = [run_baseline(FIXTURES) for _ in range(10)]
    first = runs[0]
    second = runs[-1]
    assert first["scenario_count"] == 12
    assert first["evidence_coverage"] == second["evidence_coverage"] == 1.0
    assert all(
        [item["actions"] for item in run["scenarios"]]
        == [item["actions"] for item in first["scenarios"]]
        for run in runs
    )
    assert all(item["interruption_rate"] >= 0 for item in first["scenarios"])
