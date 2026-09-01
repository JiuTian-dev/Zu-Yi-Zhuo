"""Run the isolated active-demand second-entry demo."""

import json

from app.demo.intent import run_intent_demo


def main() -> None:
    print(json.dumps(run_intent_demo(), ensure_ascii=False))


if __name__ == "__main__":
    main()
