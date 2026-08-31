"""Vendor-neutral candidate source boundary.

The adapter owns platform authorization and retrieval.  The orchestrator only
accepts normalized ParticipantSeed records, so no undocumented Zhihu endpoint
or access token can leak into matching or the conversation state machine.
"""

from collections.abc import Sequence
from typing import Protocol

from app.domain import ContentSignal, ParticipantSeed, PersonalContextSignal


class CandidateSourceError(RuntimeError):
    """Raised when an external candidate source cannot fulfill a search."""


class ContentSignalSourceError(RuntimeError):
    """Raised when an external public-content source cannot fulfill a search."""


class PersonalContextSourceError(RuntimeError):
    """Raised when an authorized personal-context source cannot fulfill a search."""


class CandidateSource(Protocol):
    async def search(self, *, query: str, limit: int) -> Sequence[ParticipantSeed]:
        """Return at most ``limit`` authorized, normalized candidate seeds."""


class ContentSignalSource(Protocol):
    async def search(self, *, query: str, limit: int) -> Sequence[ContentSignal]:
        """Return at most ``limit`` authorized public content signals."""


class PersonalContextSource(Protocol):
    async def search(
        self, *, viewer_id: str, query: str, limit: int
    ) -> Sequence[PersonalContextSignal]:
        """Return at most ``limit`` private signals owned by ``viewer_id``."""


__all__ = (
    "CandidateSource",
    "CandidateSourceError",
    "ContentSignalSource",
    "ContentSignalSourceError",
    "PersonalContextSource",
    "PersonalContextSourceError",
)
