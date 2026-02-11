"""
Sources router -- CRUD, manual fetch, fetch-logs, and raw-items for sources.

All endpoints require admin authentication.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db
from api.models import FetchLog, RawItem, Source
from api.schemas import SourceCreate, SourceUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["sources"],
    dependencies=[Depends(get_current_admin)],
)


# -- GET /sources ----------------------------------------------------------


@router.get("", response_model=None)
async def list_sources(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return all sources ordered alphabetically by name."""

    result = await db.execute(select(Source).order_by(Source.name))
    return list(result.scalars().all())


# -- GET /sources/{source_id} ---------------------------------------------


@router.get("/{source_id}", response_model=None)
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return a single source by UUID, or 404."""

    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found",
        )
    return source


# -- POST /sources ---------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED, response_model=None)
async def create_source(
    body: SourceCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new source."""

    source = Source(**body.model_dump())
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return source


# -- PUT /sources/{source_id} ----------------------------------------------


@router.put("/{source_id}", response_model=None)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Partially update an existing source (only supplied fields are changed)."""

    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(source, field_name, value)

    await db.flush()
    await db.refresh(source)
    return source


# -- DELETE /sources/{source_id} -------------------------------------------


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a source and its associated fetch logs.

    Raw items cascade-delete via the FK ``ondelete=CASCADE`` in the model,
    but we explicitly remove fetch logs here for clarity.
    """

    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found",
        )

    # Delete related fetch logs explicitly
    await db.execute(
        delete(FetchLog).where(FetchLog.source_id == source_id)
    )
    await db.delete(source)
    await db.flush()


# -- POST /sources/{source_id}/fetch-now -----------------------------------


@router.post("/{source_id}/fetch-now")
async def fetch_now(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger an immediate fetch for this source.

    Runs the fetcher inline, stores a FetchLog entry, and returns a preview
    of the first five items (title + url only).
    """

    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found",
        )

    started_at = datetime.datetime.now(datetime.timezone.utc)
    fetched_items: list[dict[str, str]] = []
    error_message: str | None = None
    fetch_status = "success"

    try:
        import aiohttp
        from api.worker.fetchers import get_fetcher

        # Build source dict for the fetcher
        source_dict: dict[str, Any] = {
            "id": str(source.id),
            "name": source.name,
            "type": source.type,
            "base_url": source.base_url,
            "endpoints": source.endpoints or [],
            "method": source.method or "GET",
            "headers": source.headers or {},
            "auth_config": source.auth_config or {},
        }
        # Ensure endpoints are absolute URLs
        base_url = (source_dict["base_url"] or "").rstrip("/")
        if isinstance(source_dict["endpoints"], list) and base_url:
            source_dict["endpoints"] = [
                ep if ep.startswith("http") else f"{base_url}{ep}"
                for ep in source_dict["endpoints"]
            ]

        fetcher = get_fetcher(source_dict["type"])
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "GoldMonitorWorker/1.0"},
        ) as http_session:
            raw_items = await fetcher.fetch(source_dict, http_session)

        fetched_items = [
            {"title": item.title, "url": item.url}
            for item in (raw_items or [])
        ]
    except Exception as exc:  # noqa: BLE001
        logger.exception("fetch-now failed for source %s", source_id)
        fetch_status = "error"
        error_message = str(exc)

    finished_at = datetime.datetime.now(datetime.timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    # Persist fetch log
    log = FetchLog(
        source_id=source_id,
        started_at=started_at,
        finished_at=finished_at,
        status=fetch_status,
        items_fetched_count=len(fetched_items),
        error_message=error_message,
        duration_ms=duration_ms,
    )
    db.add(log)
    await db.flush()

    # Update source tracking fields
    source.last_fetched_at = finished_at
    if fetch_status == "success":
        source.last_success_at = finished_at
        source.last_error = None
    else:
        source.last_error = error_message
    await db.flush()

    preview = fetched_items[:5]
    return {
        "source_id": str(source_id),
        "status": fetch_status,
        "items_fetched": len(fetched_items),
        "preview": preview,
        "duration_ms": duration_ms,
        "error": error_message,
    }


# -- POST /sources/{source_id}/fetch (alias for fetch-now) -----------------


@router.post("/{source_id}/fetch")
async def fetch_now_alias(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Alias for fetch-now (frontend calls /fetch)."""
    return await fetch_now(source_id, db)


# -- GET /sources/{source_id}/logs -----------------------------------------


@router.get("/{source_id}/logs", response_model=None)
async def get_source_logs(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return fetch logs for a source, newest first, limited to 50."""

    # Verify source exists
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found",
        )

    stmt = (
        select(FetchLog)
        .where(FetchLog.source_id == source_id)
        .order_by(desc(FetchLog.started_at))
        .limit(50)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# -- GET /sources/{source_id}/raw-items ------------------------------------


@router.get("/{source_id}/raw-items", response_model=None)
async def get_source_raw_items(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, description="Search in title or content_text"),
) -> Any:
    """Return raw items from a source, newest first, limited to 50."""

    # Verify source exists
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found",
        )

    stmt = select(RawItem).where(RawItem.source_id == source_id)

    if search is not None:
        from sqlalchemy import or_

        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                RawItem.title.ilike(pattern),
                RawItem.content_text.ilike(pattern),
            )
        )

    stmt = stmt.order_by(desc(RawItem.fetched_at)).limit(50)
    result = await db.execute(stmt)
    return list(result.scalars().all())
