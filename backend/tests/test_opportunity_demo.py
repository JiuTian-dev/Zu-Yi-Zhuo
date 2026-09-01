import json
import sys

from app.cli.opportunity_demo import DEFAULT_QUERY, main
from app.demo.public_signals import flagship_public_signals
from app.domain import OpportunityRequest
from app.opportunities import build_opportunity_preview


def test_flagship_public_signals_are_public_and_form_an_explainable_opportunity() -> None:
    assert len(flagship_public_signals) == 4
    assert {signal.visibility for signal in flagship_public_signals} == {"public"}

    preview = build_opportunity_preview(OpportunityRequest(
        query=DEFAULT_QUERY,
        signals=list(flagship_public_signals),
    ))

    assert preview.core_question == DEFAULT_QUERY
    assert len(preview.signal_ids) == 4
    assert preview.unfinishedness
    assert preview.candidates
    assert "实践者" in preview.role_gaps
    payload = preview.model_dump(mode="json")
    assert "private_stance" not in json.dumps(payload, ensure_ascii=False)
    assert all(signal["visibility"] == "public" for signal in payload["source_signals"])


def test_opportunity_demo_cli_is_deterministic_and_outputs_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["opportunity_demo"])

    main()
    first = json.loads(capsys.readouterr().out)
    main()
    second = json.loads(capsys.readouterr().out)

    assert first == second
    assert first["core_question"] == DEFAULT_QUERY
    assert len(first["source_signals"]) == 4
    assert all(signal["visibility"] == "public" for signal in first["source_signals"])
