"""Signed httpOnly cookie for chat sessions.

Uses HMAC-SHA256 with SECRET_KEY to sign the session UUID.
Format: ``session_id.hmac_sig`` (truncated to 32 hex chars).
"""

from __future__ import annotations

import hashlib
import hmac

from api.config import settings


def sign_session_id(session_id: str) -> str:
    """Return ``session_id.hmac_sig``."""
    sig = hmac.new(
        settings.SECRET_KEY.encode(),
        session_id.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"{session_id}.{sig}"


def verify_session_cookie(cookie_value: str) -> str | None:
    """Verify HMAC and return session_id, or None if invalid."""
    if not cookie_value or "." not in cookie_value:
        return None
    session_id, sig = cookie_value.rsplit(".", 1)
    expected = hmac.new(
        settings.SECRET_KEY.encode(),
        session_id.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]
    if hmac.compare_digest(sig, expected):
        return session_id
    return None
