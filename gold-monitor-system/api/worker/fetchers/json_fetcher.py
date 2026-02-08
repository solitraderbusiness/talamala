"""
JSON API fetcher.

Fetches a JSON endpoint and maps response fields to ``RawItem`` attributes
using configurable field names stored in ``source.metadata``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from api.worker.fetchers.base import BaseFetcher, RawItem

logger = logging.getLogger(__name__)

# Default field names when no mapping is provided.
_DEFAULT_TITLE_FIELD = "title"
_DEFAULT_URL_FIELD = "url"
_DEFAULT_CONTENT_FIELD = "content"
_DEFAULT_DATE_FIELD = "published_at"


class JSONFetcher(BaseFetcher):
    """Fetch items from a JSON API endpoint."""

    async def fetch(self, source: dict, http_session) -> list[RawItem]:
        endpoints = _normalise_endpoints(source.get("endpoints", []))
        meta = source.get("metadata") or {}
        items: list[RawItem] = []

        for url in endpoints:
            try:
                raw_items = await self._fetch_json(url, http_session, meta)
                items.extend(raw_items)
            except Exception:
                logger.exception("JSON fetch failed for endpoint %s", url)

        return items

    # ------------------------------------------------------------------

    async def _fetch_json(
        self,
        url: str,
        http_session,
        meta: dict[str, Any],
    ) -> list[RawItem]:
        async with http_session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

        records = _extract_records(data, meta)
        if not records:
            logger.debug("No records found in JSON response from %s", url)
            return []

        title_field = meta.get("title_field", _DEFAULT_TITLE_FIELD)
        url_field = meta.get("url_field", _DEFAULT_URL_FIELD)
        content_field = meta.get("content_field", _DEFAULT_CONTENT_FIELD)
        date_field = meta.get("date_field", _DEFAULT_DATE_FIELD)

        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue

            title = _get_nested(record, title_field, "")
            item_url = _get_nested(record, url_field, url)
            content_text = _get_nested(record, content_field, "")
            raw_date = _get_nested(record, date_field, None)

            # Coerce content to string
            if not isinstance(content_text, str):
                content_text = str(content_text) if content_text else ""
            if not isinstance(title, str):
                title = str(title) if title else ""

            published_at = _parse_date(raw_date)

            # Collect extra fields as metadata
            known_fields = {title_field, url_field, content_field, date_field}
            extra = {
                k: v
                for k, v in record.items()
                if k not in known_fields
            }

            items.append(
                RawItem(
                    title=title.strip(),
                    url=str(item_url).strip(),
                    content_text=content_text.strip(),
                    published_at=published_at,
                    metadata=extra,
                )
            )

        logger.debug("Parsed %d records from JSON endpoint %s", len(items), url)
        return items


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalise_endpoints(endpoints: Any) -> list[str]:
    if isinstance(endpoints, str):
        return [endpoints]
    if isinstance(endpoints, list):
        result: list[str] = []
        for ep in endpoints:
            if isinstance(ep, str):
                result.append(ep)
            elif isinstance(ep, dict) and "url" in ep:
                result.append(ep["url"])
        return result
    return []


def _extract_records(data: Any, meta: dict) -> list[dict]:
    """Turn the API response into a flat list of dicts.

    If ``meta["items_path"]`` is set (e.g. ``"data.articles"``), it is used
    to drill into nested structures.  Otherwise:

    * A top-level list is returned as-is.
    * A top-level dict is wrapped in a single-element list.
    """
    items_path = meta.get("items_path")
    if items_path:
        obj = data
        for key in items_path.split("."):
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                return []
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [obj]
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _get_nested(record: dict, field: str, default: Any) -> Any:
    """Resolve a possibly dot-separated field path inside *record*."""
    if "." not in field:
        return record.get(field, default)
    obj: Any = record
    for part in field.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return default
    return obj if obj is not None else default


def _parse_date(raw: Any) -> datetime | None:
    """Best-effort ISO-8601 / epoch date parsing."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        # Try ISO-8601 variants
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
    return None
