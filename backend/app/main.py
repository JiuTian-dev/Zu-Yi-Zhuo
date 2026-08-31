"""Deployment entrypoint for the conversation orchestrator API.

Run from ``backend/`` with ``uvicorn app.main:app``. Set
``TABLE_REPOSITORY_PATH`` to opt into the atomic JSON repository; leaving it
unset keeps the lightweight in-memory mode used by tests and local demos.
"""

import os

from app.api.app import create_app
from app.api.repository import JsonTableRepository


def _build_app():
    path = os.environ.get("TABLE_REPOSITORY_PATH", "").strip()
    repository = JsonTableRepository(path) if path else None
    return create_app(repository)


app = _build_app()

__all__ = ("app",)
