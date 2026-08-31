"""Explainable first-stage candidate matching."""

from .engine import build_match_plan, infer_role_gaps, recommend_candidates

__all__ = ("build_match_plan", "infer_role_gaps", "recommend_candidates")
