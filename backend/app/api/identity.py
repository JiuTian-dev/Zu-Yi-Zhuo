"""Optional server-side identity resolution for self-scoped API boundaries."""

from collections.abc import Callable
from typing import TypeAlias

from fastapi import HTTPException, Request, WebSocket

IdentityInput: TypeAlias = Request | WebSocket
IdentityResolver: TypeAlias = Callable[[IdentityInput], str | None]
ModeratorResolver: TypeAlias = Callable[[Request], str | None]


def require_request_identity(
    resolver: IdentityResolver | None,
    request: Request,
    declared_id: str,
) -> None:
    """Require an injected authenticated subject to match a caller declaration.

    The resolver is intentionally optional: development deployments continue to
    use the existing explicit ``viewer_id``/``participant_id`` contract. Once a
    resolver is configured, route parameters become claims to cross-check rather
    than credentials.
    """
    if resolver is None:
        return
    try:
        subject = resolver(request)
    except Exception as error:
        raise HTTPException(status_code=401, detail="authentication required") from error
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=401, detail="authentication required")
    if subject != declared_id:
        raise HTTPException(status_code=403, detail="authenticated subject does not match caller")


def websocket_identity_error(
    resolver: IdentityResolver | None,
    websocket: WebSocket,
    declared_id: str,
) -> str | None:
    """Return a structured handshake error code, or ``None`` when authorized."""
    if resolver is None:
        return None
    try:
        subject = resolver(websocket)
    except Exception:
        return "authentication_required"
    if not isinstance(subject, str) or not subject.strip():
        return "authentication_required"
    if subject != declared_id:
        return "identity_mismatch"
    return None


def require_moderator_identity(resolver: ModeratorResolver, request: Request) -> str:
    """Resolve a trusted moderator subject without accepting client claims."""
    try:
        subject = resolver(request)
    except Exception as error:
        raise HTTPException(status_code=401, detail="moderator authentication required") from error
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=401, detail="moderator authentication required")
    return subject.strip()


__all__ = (
    "IdentityInput",
    "IdentityResolver",
    "ModeratorResolver",
    "require_moderator_identity",
    "require_request_identity",
    "websocket_identity_error",
)
