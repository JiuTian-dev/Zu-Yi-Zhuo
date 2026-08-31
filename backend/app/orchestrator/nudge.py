"""Deterministic decision for an explicit cold-start nudge request."""

from app.domain import Action, GateDecision, RouteDecision, TableState


def build_nudge_decision(
    state: TableState, evidence_turn: int
) -> tuple[GateDecision, RouteDecision]:
    """Return one gentle Probe grounded in the latest committed human turn."""
    if evidence_turn <= 0:
        raise ValueError("nudge evidence turn must be positive")
    gate = GateDecision(
        should_speak=True,
        evidence_turns=[evidence_turn],
        reasons_to_speak=["首条表达暂未获得自然回应，主动递一句轻问"],
        reasons_to_stay_silent=[],
        confidence=.72,
    )
    route = RouteDecision(
        action=Action.PROBE,
        evidence_turns=[evidence_turn],
        confidence=.72,
    )
    return gate, route
