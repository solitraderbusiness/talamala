"""Gold videos API — list, detail, live streams, chat, and admin endpoints.

All endpoints return graceful empty responses when no data exists.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, cast, desc, func, select, update
from sqlalchemy.dialects.postgresql import JSONB

from api.videos.config import (
    CATEGORY_LABELS_FA,
    CHAT_RATE_LIMIT_PER_VIDEO_IP_DAY,
    OPENROUTER_API_KEY,
    OUTLOOK_LABELS_FA,
    TOPIC_LABELS_FA,
    TRANSCRIPT_MAX_CHARS,
    VIDEO_CHAT_SYSTEM_PROMPT,
    VIDEO_LLM_MAX_TOKENS,
    VIDEO_LLM_MODEL,
    VIDEO_LLM_TEMPERATURE,
)
from api.videos.models import (
    CuratedVideo,
    LiveStreamChannel,
    MonitoredYoutubeChannel,
    VideoChatLog,
)
from api.videos.youtube_utils import (
    extract_youtube_id,
    format_duration,
    format_view_count,
    get_embed_url,
    get_thumbnail_url,
    get_watch_url,
)
from api.auth import get_current_admin
from api.database import AsyncSessionLocal

router = APIRouter(tags=["videos"])
logger = logging.getLogger("gold_monitor.videos")


# ── Helpers ─────────────────────────────────────────────────────────────

def _video_to_dict(video: CuratedVideo) -> dict:
    """Convert a CuratedVideo ORM instance to a response dict."""
    return {
        "id": video.id,
        "youtube_id": video.youtube_id,
        "title_original": video.title_original,
        "title_fa": video.title_fa,
        "channel_name": video.channel_name,
        "channel_id": video.channel_id,
        "thumbnail_url": video.thumbnail_url or get_thumbnail_url(video.youtube_id),
        "embed_url": get_embed_url(video.youtube_id),
        "watch_url": get_watch_url(video.youtube_id),
        "duration_seconds": video.duration_seconds,
        "duration_formatted": format_duration(video.duration_seconds),
        "view_count": video.view_count,
        "view_count_formatted": format_view_count(video.view_count),
        "published_at": video.published_at.isoformat() if video.published_at else None,
        "summary_fa": video.summary_fa,
        "key_points_fa": video.key_points_fa or [],
        "topics": video.topics or [],
        "topics_fa": [TOPIC_LABELS_FA.get(t, t) for t in (video.topics or [])],
        "category": video.category,
        "category_fa": CATEGORY_LABELS_FA.get(video.category or "", ""),
        "gold_outlook": video.gold_outlook,
        "gold_outlook_fa": OUTLOOK_LABELS_FA.get(video.gold_outlook or "", ""),
        "relevance_score": video.relevance_score,
        "is_featured": video.is_featured,
        "is_published": video.is_published,
        "has_transcript": bool(video.transcript),
        "added_by": video.added_by,
        "created_at": video.created_at.isoformat() if video.created_at else None,
    }


def _get_client_ip(request: Request) -> str:
    """Get client IP from request headers or connection."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ══════════════════════════════════════════════════════════════════════════
#  1. GET /videos — paginated list with filters
# ══════════════════════════════════════════════════════════════════════════

@router.get("/videos")
async def list_videos(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    category: str | None = Query(None),
    topic: str | None = Query(None),
    outlook: str | None = Query(None),
    featured: bool | None = Query(None),
):
    """Paginated list of published videos with filters."""
    async with AsyncSessionLocal() as session:
        q = select(CuratedVideo).where(CuratedVideo.is_published.is_(True))

        if category and category in CATEGORY_LABELS_FA:
            q = q.where(CuratedVideo.category == category)

        if topic:
            q = q.where(CuratedVideo.topics.op("@>")(cast(f'["{topic}"]', JSONB)))

        if outlook and outlook in ("bullish", "bearish", "neutral", "mixed"):
            q = q.where(CuratedVideo.gold_outlook == outlook)

        if featured is True:
            q = q.where(CuratedVideo.is_featured.is_(True))

        # Count total
        count_q = select(func.count()).select_from(q.subquery())
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * per_page
        q = q.order_by(desc(CuratedVideo.published_at).nullslast()).offset(offset).limit(per_page)
        result = await session.execute(q)
        videos = result.scalars().all()

        return {
            "videos": [_video_to_dict(v) for v in videos],
            "total": total,
            "page": page,
            "per_page": per_page,
        }


# ══════════════════════════════════════════════════════════════════════════
#  2. GET /videos/live-streams — active live stream channels
# ══════════════════════════════════════════════════════════════════════════

@router.get("/videos/live-streams")
async def list_live_streams():
    """List active live stream channels ordered by sort_order."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LiveStreamChannel)
            .where(LiveStreamChannel.is_active.is_(True))
            .order_by(LiveStreamChannel.sort_order)
        )
        channels = result.scalars().all()

        return {
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "name_fa": ch.name_fa,
                    "youtube_channel_id": ch.youtube_channel_id,
                    "thumbnail_url": ch.thumbnail_url,
                    "embed_url": f"https://www.youtube.com/embed/live_stream?channel={ch.youtube_channel_id}",
                }
                for ch in channels
            ],
        }


# ══════════════════════════════════════════════════════════════════════════
#  3. GET /videos/{video_id} — full detail with related videos
# ══════════════════════════════════════════════════════════════════════════

@router.get("/videos/{video_id}")
async def get_video(video_id: int):
    """Full video detail with related videos."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CuratedVideo).where(CuratedVideo.id == video_id)
        )
        video = result.scalar_one_or_none()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        video_dict = _video_to_dict(video)
        # Include transcript in detail view only (not in list)
        video_dict["transcript"] = video.transcript

        # Find related videos (same topics, recent)
        related = []
        if video.topics:
            for topic_slug in (video.topics or [])[:2]:
                related_q = await session.execute(
                    select(CuratedVideo)
                    .where(
                        CuratedVideo.id != video.id,
                        CuratedVideo.is_published.is_(True),
                        CuratedVideo.topics.op("@>")(cast(f'["{topic_slug}"]', JSONB)),
                    )
                    .order_by(desc(CuratedVideo.created_at))
                    .limit(3)
                )
                for r in related_q.scalars().all():
                    if r.id not in [x["id"] for x in related]:
                        related.append(_video_to_dict(r))
                        if len(related) >= 4:
                            break
                if len(related) >= 4:
                    break

        video_dict["related_videos"] = related[:4]

        return video_dict


# ══════════════════════════════════════════════════════════════════════════
#  4. POST /videos/{video_id}/chat — per-video Q&A
# ══════════════════════════════════════════════════════════════════════════

class VideoChatRequest(BaseModel):
    question: str


@router.post("/videos/{video_id}/chat")
async def video_chat(video_id: int, body: VideoChatRequest, request: Request):
    """Per-video Q&A chat using transcript context."""
    ip = _get_client_ip(request)

    # Rate limit check
    async with AsyncSessionLocal() as session:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        count_result = await session.execute(
            select(func.count()).where(
                VideoChatLog.video_id == video_id,
                VideoChatLog.ip_address == ip,
                VideoChatLog.created_at >= today_start,
            )
        )
        count = count_result.scalar() or 0
        if count >= CHAT_RATE_LIMIT_PER_VIDEO_IP_DAY:
            raise HTTPException(
                status_code=429,
                detail="محدودیت تعداد سوال روزانه. لطفا فردا دوباره تلاش کنید.",
            )

    # Get video with transcript
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CuratedVideo).where(CuratedVideo.id == video_id)
        )
        video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if not video.transcript:
        raise HTTPException(
            status_code=400,
            detail="متن این ویدیو در دسترس نیست.",
        )

    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="Chat service unavailable")

    # Build prompt
    system_prompt = VIDEO_CHAT_SYSTEM_PROMPT.format(
        title=video.title_original or video.youtube_id,
        channel=video.channel_name or "Unknown",
        transcript=video.transcript[:TRANSCRIPT_MAX_CHARS],
    )

    import httpx

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://gold-monitor.local",
        "X-Title": "Gold Monitor Video Chat",
    }

    payload = {
        "model": VIDEO_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": body.question},
        ],
        "temperature": VIDEO_LLM_TEMPERATURE,
        "max_tokens": VIDEO_LLM_MAX_TOKENS,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            logger.error("Chat LLM error: HTTP %d", response.status_code)
            raise HTTPException(status_code=502, detail="Chat service error")

        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
        tokens = data.get("usage", {}).get("total_tokens")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Chat service timeout")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail="Chat service error")

    # Log the chat
    async with AsyncSessionLocal() as session:
        session.add(VideoChatLog(
            video_id=video_id,
            ip_address=ip,
            question=body.question[:2000],
            answer=answer[:5000],
            tokens_used=tokens,
        ))
        await session.commit()

    return {"answer": answer}


# ══════════════════════════════════════════════════════════════════════════
#  5. Admin endpoints
# ══════════════════════════════════════════════════════════════════════════

class AdminAddVideoRequest(BaseModel):
    url: str


class AdminUpdateVideoRequest(BaseModel):
    is_published: bool | None = None
    is_featured: bool | None = None
    deleted: bool | None = None


class AdminAddChannelRequest(BaseModel):
    name: str
    youtube_channel_id: str
    always_relevant: bool = False
    auto_publish: bool = False


class AdminUpdateChannelRequest(BaseModel):
    is_active: bool | None = None
    auto_publish: bool | None = None
    always_relevant: bool | None = None


@router.post("/admin/videos", dependencies=[Depends(get_current_admin)])
async def admin_add_video(body: AdminAddVideoRequest):
    """Add a video by URL (admin auth required)."""

    youtube_id = extract_youtube_id(body.url)
    if not youtube_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(CuratedVideo).where(CuratedVideo.youtube_id == youtube_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Video already exists")

        video = CuratedVideo(
            youtube_id=youtube_id,
            added_by="admin",
            is_published=False,
            llm_processed=False,
        )
        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {"id": video.id, "youtube_id": youtube_id, "status": "added"}


@router.patch("/admin/videos/{video_id}", dependencies=[Depends(get_current_admin)])
async def admin_update_video(video_id: int, body: AdminUpdateVideoRequest):
    """Toggle published/featured or delete a video (admin auth required)."""

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CuratedVideo).where(CuratedVideo.id == video_id)
        )
        video = result.scalar_one_or_none()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        if body.deleted:
            await session.delete(video)
            await session.commit()
            return {"status": "deleted"}

        values = {}
        if body.is_published is not None:
            values["is_published"] = body.is_published
        if body.is_featured is not None:
            values["is_featured"] = body.is_featured
        if values:
            values["updated_at"] = datetime.now(timezone.utc)
            await session.execute(
                update(CuratedVideo)
                .where(CuratedVideo.id == video_id)
                .values(**values)
            )
            await session.commit()

        return {"status": "updated"}


@router.post("/admin/videos/{video_id}/regenerate", dependencies=[Depends(get_current_admin)])
async def admin_regenerate_video(video_id: int):
    """Re-run transcript + summary for a video (admin auth required)."""

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(CuratedVideo)
            .where(CuratedVideo.id == video_id)
            .values(
                llm_processed=False,
                transcript=None,
                summary_fa=None,
                key_points_fa=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    return {"status": "queued_for_regeneration"}


@router.post("/admin/videos/reprocess-title-only", dependencies=[Depends(get_current_admin)])
async def admin_reprocess_title_only():
    """Reset videos scored without transcripts so they get re-processed.

    Finds published videos where llm_processed=True but transcript is NULL
    (meaning they were scored with title-only) and resets them for reprocessing.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).where(
                CuratedVideo.llm_processed.is_(True),
                CuratedVideo.transcript.is_(None),
            )
        )
        count = result.scalar() or 0

        if count > 0:
            await session.execute(
                update(CuratedVideo)
                .where(
                    CuratedVideo.llm_processed.is_(True),
                    CuratedVideo.transcript.is_(None),
                )
                .values(
                    llm_processed=False,
                    summary_fa=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    return {"status": "queued", "count": count}


@router.get("/admin/videos/channels", dependencies=[Depends(get_current_admin)])
async def admin_list_channels():
    """List monitored YouTube channels (admin auth required)."""

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MonitoredYoutubeChannel).order_by(MonitoredYoutubeChannel.name)
        )
        channels = result.scalars().all()

        return {
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "youtube_channel_id": ch.youtube_channel_id,
                    "is_active": ch.is_active,
                    "auto_publish": ch.auto_publish,
                    "always_relevant": ch.always_relevant,
                    "last_checked_at": ch.last_checked_at.isoformat() if ch.last_checked_at else None,
                    "created_at": ch.created_at.isoformat() if ch.created_at else None,
                }
                for ch in channels
            ],
        }


@router.post("/admin/videos/channels", dependencies=[Depends(get_current_admin)])
async def admin_add_channel(body: AdminAddChannelRequest):
    """Add a monitored YouTube channel (admin auth required)."""

    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(MonitoredYoutubeChannel).where(
                MonitoredYoutubeChannel.youtube_channel_id == body.youtube_channel_id
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Channel already exists")

        channel = MonitoredYoutubeChannel(
            name=body.name,
            youtube_channel_id=body.youtube_channel_id,
            always_relevant=body.always_relevant,
            auto_publish=body.auto_publish,
        )
        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {"id": channel.id, "name": channel.name, "status": "added"}


@router.patch("/admin/videos/channels/{channel_id}", dependencies=[Depends(get_current_admin)])
async def admin_update_channel(channel_id: int, body: AdminUpdateChannelRequest):
    """Toggle active/auto_publish for a channel (admin auth required)."""

    async with AsyncSessionLocal() as session:
        values = {}
        if body.is_active is not None:
            values["is_active"] = body.is_active
        if body.auto_publish is not None:
            values["auto_publish"] = body.auto_publish
        if body.always_relevant is not None:
            values["always_relevant"] = body.always_relevant
        if values:
            await session.execute(
                update(MonitoredYoutubeChannel)
                .where(MonitoredYoutubeChannel.id == channel_id)
                .values(**values)
            )
            await session.commit()

        return {"status": "updated"}
