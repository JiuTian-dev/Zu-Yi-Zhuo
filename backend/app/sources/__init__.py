"""Candidate-source contracts for official Zhihu CLI/MCP/OAuth adapters."""

from .base import CandidateSource, CandidateSourceError, ContentSignalSource, ContentSignalSourceError
from .content import CommandContentSignalSource
from .command import CommandCandidateSource

__all__ = (
    "CandidateSource",
    "CandidateSourceError",
    "CommandCandidateSource",
    "CommandContentSignalSource",
    "ContentSignalSource",
    "ContentSignalSourceError",
)
