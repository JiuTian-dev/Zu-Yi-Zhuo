"""Offline baseline runner for the pre-Multi-Agent deterministic loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from app.domain import HumanTurn, ParticipantSeed
from app.orchestrator import build_initial_state, decide_intervention, observe_turn


def load_fixtures(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("scenarios"), list):
        raise ValueError("fixture manifest must contain scenarios[]")
    scenarios = payload["scenarios"]
    if len(scenarios) != 12:
        raise ValueError("baseline manifest must contain exactly 12 scenarios")
    return scenarios


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    participants = [ParticipantSeed.model_validate(item) for item in scenario["participants"]]
    state = build_initial_state(scenario["name"], scenario["core_question"], participants)
    turns = scenario["turns"]
    actions: list[str] = []
    evidence_covered = 0
    durations: list[float] = []
    for turn_number, item in enumerate(turns, start=1):
        started = perf_counter()
        turn = HumanTurn(turn_id=turn_number, participant_id=item["participant_id"], text=item["text"])
        state = observe_turn(state, turn)
        gate, route = decide_intervention(state)
        if route.action.value != "SILENCE":
            actions.append(route.action.value)
            if route.evidence_turns and all(evidence <= turn_number for evidence in route.evidence_turns):
                evidence_covered += 1
        durations.append((perf_counter() - started) * 1000)
    expected = scenario.get("expected", {})
    expected_actions = set(expected.get("allowed_actions", []))
    action_hit = 1.0 if not expected_actions or expected_actions.intersection(actions) else 0.0
    return {
        "name": scenario["name"],
        "turns": len(turns),
        "actions": actions,
        "action_count": len(actions),
        "evidence_coverage": evidence_covered / len(actions) if actions else 1.0,
        "action_hit": action_hit,
        "interruption_rate": len(actions) / len(turns) if turns else 0.0,
        "p50_latency_ms": round(median(durations), 3) if durations else 0.0,
        "p95_latency_ms": round(sorted(durations)[max(0, int(len(durations) * 0.95) - 1)], 3) if durations else 0.0,
        "labels": expected.get("labels", []),
    }


def run_baseline(path: Path) -> dict[str, Any]:
    scenarios = load_fixtures(path)
    results = [run_scenario(scenario) for scenario in scenarios]
    latencies = [result["p95_latency_ms"] for result in results]
    return {
        "runner": "deterministic-pre-multi-agent",
        "scenario_count": len(results),
        "evidence_coverage": round(sum(item["evidence_coverage"] for item in results) / len(results), 4),
        "action_hit_rate": round(sum(item["action_hit"] for item in results) / len(results), 4),
        "interruption_rate": round(sum(item["interruption_rate"] for item in results) / len(results), 4),
        "p50_latency_ms": round(median(latencies), 3),
        "p95_latency_ms": round(max(latencies), 3),
        "scenarios": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).parents[2] / "tests" / "fixtures" / "multi_agent" / "manifest.json")
    args = parser.parse_args()
    print(json.dumps(run_baseline(args.fixtures), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
