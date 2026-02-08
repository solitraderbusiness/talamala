"""
JWT authentication utilities and FastAPI dependency for admin access.

* Password hashing via **passlib** (bcrypt).
* Token creation / verification via **python-jose** (HS256).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.models import AdminUser

# ── Password hashing ───────────────────────────────────────────────────

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate_for_bcrypt(password: str) -> str:
    """Truncate password to 72 bytes (bcrypt limit)."""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash for *password*."""
    return _pwd_ctx.hash(_truncate_for_bcrypt(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` when *plain_password* matches *hashed_password*."""
    return _pwd_ctx.verify(_truncate_for_bcrypt(plain_password), hashed_password)


# ── JWT tokens ──────────────────────────────────────────────────────────

_ALGORITHM = "HS256"


def create_access_token(email: str) -> str:
    """Create a signed JWT containing the admin *email* as ``sub``."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    payload = {
        "sub": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def verify_token(token: str) -> str:
    """Decode *token* and return the ``sub`` (email).

    Raises ``HTTPException(401)`` on any failure.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing 'sub' claim.",
            )
        return email
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        ) from exc


# ── FastAPI dependency ──────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """Validate the JWT from the ``Authorization: Bearer <token>`` header
    and return the corresponding :class:`AdminUser` row.

    Raises 401 if the token is invalid or the user does not exist.
    """
    email = verify_token(credentials.credentials)

    result = await db.execute(
        select(AdminUser).where(AdminUser.email == email),
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found.",
        )

    return user
