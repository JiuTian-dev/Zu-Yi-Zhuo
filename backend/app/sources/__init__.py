"""Candidate-source contracts for official Zhihu CLI/MCP/OAuth adapters."""

from .base import CandidateSource, CandidateSourceError
from .command import CommandCandidateSource

__all__ = ("CandidateSource", "CandidateSourceError", "CommandCandidateSource")
