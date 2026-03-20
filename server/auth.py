"""
Request authentication helper.

If SECRET_KEY is the default ``"change-me"`` all requests are allowed through.
Otherwise the caller must supply ``Authorization: Bearer <key>``.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from .config import settings


def check_auth(request: Request) -> None:
    if settings.SECRET_KEY == "change-me":
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if auth.removeprefix("Bearer ").strip() != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid token")
