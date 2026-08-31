"""Vendor-neutral candidate source boundary.

The adapter owns platform authorization and retrieval.  The orchestrator only
accepts normalized ParticipantSeed records, so no undocumented Zhihu endpoint
or access token can leak into matching or the conversation state machine.
"""

from collections.abc import Sequence
from typing import Protocol

from app.domain import ParticipantSeed


class CandidateSourceError(RuntimeError):
    """Raised when an external candidate source cannot fulfill a search."""


class CandidateSource(Protocol):
    async def search(self, *, query: str, limit: int) -> Sequence[ParticipantSeed]:
        """Return at most ``limit`` authorized, normalized candidate seeds."""


__all__ = ("CandidateSource", "CandidateSourceError")
