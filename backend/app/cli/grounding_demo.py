"""Run the isolated source-grounded conversation demo."""

import json

from app.demo.grounding import run_grounding_demo


def main() -> None:
    print(json.dumps(run_grounding_demo(), ensure_ascii=False))


if __name__ == "__main__":
    main()
