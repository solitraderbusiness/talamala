"""
Base fetcher interface and shared data structures.

Every concrete fetcher (RSS, HTML, JSON, ...) inherits from ``BaseFetcher``
and returns a list of ``RawItem`` instances.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


@dataclasses.dataclass(slots=True)
class RawItem:
    """Normalised item returned by every fetcher."""

    title: str
    url: str
    content_text: str
    published_at: datetime | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


class BaseFetcher(ABC):
    """Abstract base class that all source fetchers must implement."""

    @abstractmethod
    async def fetch(self, source: dict, http_session) -> list[RawItem]:
        """Fetch and parse items from *source*.

        Parameters
        ----------
        source:
            A source row dict containing at least ``endpoints`` (list of
            URLs) and ``metadata`` (optional configuration).
        http_session:
            An ``aiohttp.ClientSession`` instance for making HTTP requests.

        Returns
        -------
        list[RawItem]
            Parsed items ready for storage and rule matching.
        """
        ...
