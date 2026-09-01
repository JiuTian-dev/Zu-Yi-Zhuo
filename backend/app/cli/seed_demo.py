"""Seed a repeatable three-table demo repository."""

import argparse
import json
import os
from pathlib import Path

from app.api.repository import JsonTableRepository
from app.demo.bootstrap import seed_demo_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic 组一桌 demo tables")
    parser.add_argument(
        "--path",
        default=os.getenv("TABLE_REPOSITORY_PATH"),
        help="JSON repository path (or TABLE_REPOSITORY_PATH)",
    )
    args = parser.parse_args()
    if not args.path:
        parser.error("--path is required unless TABLE_REPOSITORY_PATH is set")
    repository = JsonTableRepository(Path(args.path))
    results = seed_demo_tables(repository)
    print(json.dumps({"path": str(Path(args.path)), "tables": [item.as_dict() for item in results]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
