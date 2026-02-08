"""
Admin router -- login, settings management, and current-user info.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import create_access_token, get_current_admin, verify_password
from api.database import get_db
from api.models import AdminUser, Setting
from api.schemas import LoginRequest, SettingUpdate

router = APIRouter(tags=["admin"])


# -- POST /admin/login -----------------------------------------------------


@router.post("/login")
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Authenticate with email + password and return a JWT access token.

    Returns 401 if the credentials are invalid.
    """

    result = await db.execute(
        select(AdminUser).where(AdminUser.email == body.email)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
    }


# -- GET /admin/settings ---------------------------------------------------


@router.get("/settings", dependencies=[Depends(get_current_admin)])
async def list_settings(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return all key-value settings."""

    result = await db.execute(select(Setting).order_by(Setting.key))
    settings = result.scalars().all()
    return [{"key": s.key, "value": s.value} for s in settings]


# -- PUT /admin/settings (bulk) --------------------------------------------


@router.put("/settings", dependencies=[Depends(get_current_admin)])
async def update_settings_bulk(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bulk create/update settings.  Accepts ``{key: value, ...}``."""

    for key, value in body.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = Setting(key=key, value=value)
            db.add(setting)
        else:
            setting.value = value

    await db.commit()

    # Return the full updated settings as a flat dict
    result = await db.execute(select(Setting).order_by(Setting.key))
    settings = result.scalars().all()
    return {s.key: s.value for s in settings}


# -- PUT /admin/settings/{key} ---------------------------------------------


@router.put("/settings/{key}", dependencies=[Depends(get_current_admin)])
async def update_setting(
    key: str,
    body: SettingUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create or update a setting by key (upsert)."""

    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if setting is None:
        setting = Setting(key=key, value=body.value)
        db.add(setting)
    else:
        setting.value = body.value

    await db.flush()
    await db.refresh(setting)
    return {"key": setting.key, "value": setting.value}


# -- GET /admin/me ----------------------------------------------------------


@router.get("/me")
async def get_current_admin_info(
    current_user: AdminUser = Depends(get_current_admin),
) -> dict[str, Any]:
    """Return profile information for the currently authenticated admin."""

    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }
