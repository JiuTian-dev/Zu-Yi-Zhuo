"""Public table-state projections that preserve participant privacy."""

from app.domain import TableState


def project_state_for_viewer(state: TableState, viewer_id: str | None = None) -> TableState:
    """Hide unconsented profile fields while retaining public conversation evidence."""
    projected = state.model_copy(deep=True)
    for participant_id, participant in projected.participants.items():
        if participant_id != viewer_id and not participant.profile_shared:
            participant.declared_position = None
            participant.unused_relevant_experience = []
    return projected


__all__ = ("project_state_for_viewer",)
