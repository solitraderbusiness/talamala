"""
HTML page fetcher.

Uses ``aiohttp`` to download the page and ``BeautifulSoup`` to extract
the page title and visible text content.
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from api.worker.fetchers.base import BaseFetcher, RawItem

logger = logging.getLogger(__name__)

# Tags whose text is generally not useful to extract.
_STRIP_TAGS = frozenset({
    "script", "style", "noscript", "iframe", "svg", "head", "meta",
    "link", "template",
})


class HTMLFetcher(BaseFetcher):
    """Fetch HTML pages and extract visible text."""

    async def fetch(self, source: dict, http_session) -> list[RawItem]:
        endpoints = _normalise_endpoints(source.get("endpoints", []))
        items: list[RawItem] = []

        for url in endpoints:
            try:
                item = await self._fetch_page(url, http_session, source)
                if item is not None:
                    items.append(item)
            except Exception:
                logger.exception("HTML fetch failed for endpoint %s", url)

        return items

    # ------------------------------------------------------------------

    async def _fetch_page(
        self, url: str, http_session, source: dict
    ) -> RawItem | None:
        async with http_session.get(url) as resp:
            resp.raise_for_status()
            html = await resp.text()

        soup = BeautifulSoup(html, "lxml")

        # Remove unwanted tags before extracting text.
        for tag in soup.find_all(_STRIP_TAGS):
            tag.decompose()

        title = _extract_title(soup, url)
        content_text = _extract_text(soup, source.get("metadata") or {})

        if not content_text.strip():
            logger.debug("No text content extracted from %s", url)
            return None

        metadata: dict[str, Any] = {}
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            metadata["meta_description"] = meta_desc["content"]

        return RawItem(
            title=title,
            url=url,
            content_text=content_text,
            published_at=None,
            metadata=metadata,
        )


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


def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    """Return the page title from <title> or the first <h1>."""
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return fallback


def _extract_text(soup: BeautifulSoup, metadata: dict) -> str:
    """Extract visible text from the page.

    If ``metadata`` contains a ``css_selector`` key, only text inside matching
    elements is returned.  Otherwise the full ``<body>`` text is used.
    """
    css_selector = metadata.get("css_selector")
    if css_selector:
        selected = soup.select(css_selector)
        if selected:
            parts = [el.get_text(separator="\n", strip=True) for el in selected]
            return "\n\n".join(parts)

    body = soup.find("body")
    if body:
        return body.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)
