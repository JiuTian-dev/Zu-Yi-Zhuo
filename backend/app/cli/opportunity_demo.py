"""Print a deterministic public-signal opportunity preview for evaluator demos."""

import argparse
import json

from app.demo.public_signals import flagship_public_signals
from app.domain import OpportunityRequest
from app.opportunities import build_opportunity_preview

DEFAULT_QUERY = "AI Agent 真正进入企业，卡住的是技术还是采购？"


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview a public-signal opportunity")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="core question to preview")
    args = parser.parse_args()
    request = OpportunityRequest(query=args.query, signals=list(flagship_public_signals))
    preview = build_opportunity_preview(request)
    print(json.dumps(preview.model_dump(mode="json"), ensure_ascii=False))


if __name__ == "__main__":
    main()
