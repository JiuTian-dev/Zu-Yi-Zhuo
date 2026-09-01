"""Run the complete local backend journey and print a bounded JSON report."""

import json

from app.demo.journey import run_journey_demo


def main() -> None:
    print(json.dumps(run_journey_demo(), ensure_ascii=False))


if __name__ == "__main__":
    main()
