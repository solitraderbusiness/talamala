"""
Fetcher registry.

Use ``get_fetcher(source_type)`` to obtain the right fetcher instance for a
given source type string (``"rss"``, ``"html"``, ``"json"``).
"""

from __future__ import annotations

from api.worker.fetchers.base import BaseFetcher, RawItem
from api.worker.fetchers.html_fetcher import HTMLFetcher
from api.worker.fetchers.json_fetcher import JSONFetcher
from api.worker.fetchers.rss_fetcher import RSSFetcher

__all__ = [
    "BaseFetcher",
    "RawItem",
    "get_fetcher",
]

_FETCHER_MAP: dict[str, type[BaseFetcher]] = {
    "rss": RSSFetcher,
    "html": HTMLFetcher,
    "json": JSONFetcher,
    "json_api": JSONFetcher,
}


def get_fetcher(source_type: str) -> BaseFetcher:
    """Return a fetcher instance for the given *source_type*.

    Raises ``ValueError`` if the type is not recognised.
    """
    cls = _FETCHER_MAP.get(source_type)
    if cls is None:
        raise ValueError(
            f"Unknown source type: {source_type!r}. "
            f"Supported types: {', '.join(sorted(_FETCHER_MAP))}"
        )
    return cls()
