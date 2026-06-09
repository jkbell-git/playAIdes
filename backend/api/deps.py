"""Shared FastAPI dependencies for the api layer."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException


def require_api_key(authorization: Optional[str] = Header(default=None)):
    """Bearer-token gate. Dev mode (PLAYAIDES_API_KEY unset) = no auth (logged at
    startup elsewhere). Moved verbatim from incarnation_server._setup_routes so it
    can be reused by routers and unit-tested directly."""
    expected = os.environ.get("PLAYAIDES_API_KEY")
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.removeprefix("Bearer ") != expected:
        raise HTTPException(status_code=401, detail="invalid bearer token")
