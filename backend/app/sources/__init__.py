"""Candidate-source contracts for official Zhihu CLI/MCP/OAuth adapters."""

from .base import CandidateSource, CandidateSourceError, ContentSignalSource, ContentSignalSourceError, PersonalContextSource, PersonalContextSourceError
from .content import CommandContentSignalSource
from .command import CommandCandidateSource
from .personal import CommandPersonalContextSource
from .http import HttpCandidateSource, HttpContentSignalSource, HttpPersonalContextSource

__all__ = (
    "CandidateSource",
    "CandidateSourceError",
    "CommandCandidateSource",
    "CommandContentSignalSource",
    "ContentSignalSource",
    "ContentSignalSourceError",
    "CommandPersonalContextSource",
    "HttpCandidateSource",
    "HttpContentSignalSource",
    "HttpPersonalContextSource",
    "PersonalContextSource",
    "PersonalContextSourceError",
)
