import argparse
import json

from app.demo import SCENARIOS, flagship_participants
from app.orchestrator import build_initial_state, observe_turn

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=SCENARIOS, default="flagship")
    args = parser.parse_args()
    state = build_initial_state("demo-table", "AI Agent 真正进入企业，卡住的是技术还是采购？", flagship_participants)
    def snapshot():
        payload = state.model_dump(mode="json")
        payload["recommended_action"] = state.intervention.recommended_action.value
        return payload
    snapshots = [snapshot()]
    for turn in SCENARIOS[args.scenario]:
        state = observe_turn(state, turn)
        snapshots.append(snapshot())
    print(json.dumps(snapshots, ensure_ascii=False))

if __name__ == "__main__":
    main()
