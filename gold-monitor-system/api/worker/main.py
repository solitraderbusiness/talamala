"""
Gold Monitor Worker — periodic fetch-match-alert pipeline.

Runs continuously with a 60-second cycle:

1. Acquire a Redis distributed lock (``worker:lock``, 55 s TTL) to
   prevent overlapping runs across replicas.
2. Query enabled sources whose ``poll_interval_seconds`` has elapsed.
3. For each source, invoke the appropriate fetcher (RSS / HTML / JSON).
4. Store new ``raw_items`` (deduplicated by SHA-256 content hash).
5. Match each new item against the loaded YAML rules.
6. Determine severity, build alert, check deduplication.
7. Optionally enrich alerts with an LLM summary (OpenRouter).
8. Persist alerts and fetch-log entries.

Usage (Docker Compose)::

    python -m worker.main
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
import redis.asyncio as aioredis
import yaml
from sqlalchemy import text

from api.config import settings
from api.database import AsyncSessionLocal

from api.worker.dedup import DedupChecker
from api.worker.fetchers import get_fetcher
from api.worker.fetchers.base import RawItem

# ---------------------------------------------------------------------------
# Optional rule-engine integration (may not be deployed yet)
# ---------------------------------------------------------------------------
_rule_engine_available = False
try:
    from api.rule_engine.load_rules import (
        load_rules as _re_load_yaml,
        get_rules as _re_get_rules,
    )
    from api.rule_engine.alert_builder import build_alert as _re_build_alert
    from api.rule_engine.matcher import match_rules as _re_match_rules

    _rule_engine_available = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CYCLE_INTERVAL = 60  # seconds between cycles
LOCK_KEY = "worker:lock"
LOCK_TTL = 55  # seconds — slightly less than CYCLE_INTERVAL
FETCH_TIMEOUT = 30  # per-request HTTP timeout (seconds)
MAX_ALERTS_PER_SOURCE = 10  # prevent any single source from flooding
MIN_MATCH_SCORE = 0.15  # compound keywords prevent false positives at this threshold
HIGH_CONFIDENCE_SCORE = 0.30  # above this, skip LLM relevance check
MAX_ARTICLE_AGE_HOURS = 6  # skip RSS items older than 6 hours for freshness

logger = logging.getLogger("worker")


# ===================================================================
# Worker
# ===================================================================

class Worker:
    """Orchestrates the periodic fetch-match-alert pipeline."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._rules: list = []
        self._use_rule_engine: bool = False
        self._shutdown = asyncio.Event()
        self._http_session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to backing services, install signal handlers, and enter
        the main loop.  Blocks until shutdown is requested."""
        logger.info("Worker starting up ...")

        self._redis = aioredis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
        # Load rules as typed Rule objects when rule engine is available
        if _rule_engine_available:
            try:
                yaml_data = _re_load_yaml(settings.YAML_PATH)
                self._rules = _re_get_rules(yaml_data)
                self._use_rule_engine = True
            except Exception:
                logger.warning(
                    "Rule engine load failed — using fallback dict loader",
                    exc_info=True,
                )
                self._rules = _load_rules(settings.YAML_PATH)
                self._use_rule_engine = False
        else:
            self._rules = _load_rules(settings.YAML_PATH)
            self._use_rule_engine = False
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT),
            headers={"User-Agent": "Mozilla/5.0 (compatible; GoldMonitor/1.0)"},
        )

        # Graceful shutdown on SIGTERM / SIGINT
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._request_shutdown)

        logger.info(
            "Worker ready  (cycle=%ds, lock_ttl=%ds, rules=%d)",
            CYCLE_INTERVAL,
            LOCK_TTL,
            len(self._rules),
        )

        try:
            await self._main_loop()
        finally:
            await self._cleanup()

    def _request_shutdown(self) -> None:
        logger.info("Shutdown signal received — finishing current cycle")
        self._shutdown.set()

    async def _cleanup(self) -> None:
        logger.info("Cleaning up resources ...")
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        if self._redis:
            await self._redis.aclose()  # type: ignore[union-attr]
        logger.info("Worker stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        while not self._shutdown.is_set():
            cycle_start = time.monotonic()

            # Try to acquire the distributed lock
            try:
                acquired = await self._redis.set(  # type: ignore[union-attr]
                    LOCK_KEY, "1", nx=True, ex=LOCK_TTL
                )
            except Exception:
                logger.exception("Redis lock acquisition failed")
                await self._sleep_until_next_cycle(cycle_start)
                continue

            if not acquired:
                logger.debug("Lock held by another instance — skipping cycle")
                await self._sleep_until_next_cycle(cycle_start)
                continue

            try:
                await self._run_cycle()
            except Exception:
                logger.exception("Unhandled error during worker cycle")
            finally:
                try:
                    await self._redis.delete(LOCK_KEY)  # type: ignore[union-attr]
                except Exception:
                    logger.warning("Failed to release Redis lock", exc_info=True)

            await self._sleep_until_next_cycle(cycle_start)

    async def _sleep_until_next_cycle(self, cycle_start: float) -> None:
        elapsed = time.monotonic() - cycle_start
        remaining = max(0.0, CYCLE_INTERVAL - elapsed)
        if remaining > 0:
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=remaining
                )
            except asyncio.TimeoutError:
                pass  # Normal — the event was not set during sleep.

    # ------------------------------------------------------------------
    # Single cycle
    # ------------------------------------------------------------------

    async def _run_cycle(self) -> None:
        logger.info("=== Cycle start ===")
        async with AsyncSessionLocal() as db:
            sources = await self._get_due_sources(db)
            if not sources:
                logger.debug("No sources due for fetching")
                return

            logger.info("Sources due for fetching: %d", len(sources))
            dedup = DedupChecker(self._redis, db)  # type: ignore[arg-type]

            for source in sources:
                try:
                    await self._process_source(source, db, dedup)
                except Exception:
                    logger.exception(
                        "Error processing source %s (id=%s)",
                        source.get("name"),
                        source.get("id"),
                    )
                    # Rollback the failed transaction before recording error
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    try:
                        await self._record_source_error(
                            db,
                            source,
                            error_msg=_format_exc(),
                        )
                    except Exception:
                        logger.warning("Could not record source error", exc_info=True)

        logger.info("=== Cycle end ===")

    # ------------------------------------------------------------------
    # Source queries
    # ------------------------------------------------------------------

    async def _get_due_sources(self, db) -> list[dict[str, Any]]:
        result = await db.execute(
            text(
                "SELECT id, name, type, base_url, endpoints, method, headers, "
                "       auth_config, parser, poll_interval_seconds, "
                "       categories, rule_bindings, last_fetched_at, enabled "
                "FROM sources "
                "WHERE enabled = true "
                "  AND ("
                "    last_fetched_at IS NULL "
                "    OR EXTRACT(EPOCH FROM (NOW() - last_fetched_at)) "
                "       >= poll_interval_seconds"
                "  ) "
                "ORDER BY last_fetched_at ASC NULLS FIRST"
            )
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Per-source pipeline
    # ------------------------------------------------------------------

    async def _process_source(
        self,
        source: dict[str, Any],
        db,
        dedup: DedupChecker,
    ) -> None:
        source_id = source["id"]
        source_name = source.get("name", source_id)
        started_at = datetime.now(timezone.utc)

        logger.info("Processing source: %s (type=%s)", source_name, source["type"])

        # Normalise the endpoints column (could be a JSON string)
        endpoints = source.get("endpoints")
        if isinstance(endpoints, str):
            try:
                endpoints = json.loads(endpoints)
            except (json.JSONDecodeError, TypeError):
                endpoints = [endpoints]
            source["endpoints"] = endpoints

        # Ensure endpoints are absolute URLs (prepend base_url if relative)
        base_url = (source.get("base_url") or "").rstrip("/")
        if isinstance(source.get("endpoints"), list) and base_url:
            source["endpoints"] = [
                ep if ep.startswith("http") else f"{base_url}{ep}"
                for ep in source["endpoints"]
            ]

        # Normalise headers/auth_config
        for json_field in ("headers", "auth_config"):
            val = source.get(json_field)
            if isinstance(val, str):
                try:
                    source[json_field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    source[json_field] = {}

        # 1. Fetch
        fetcher = get_fetcher(source["type"])
        raw_items = await fetcher.fetch(source, self._http_session)
        logger.info(
            "Fetched %d items from source %s", len(raw_items), source_name
        )

        # 2-6. Process each item
        new_count = 0
        matched_count = 0
        age_cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
        for item in raw_items:
            # Skip old articles (e.g. Google News returning months-old results)
            if item.published_at and item.published_at < age_cutoff:
                continue

            content_hash = _compute_content_hash(item)

            # 3. Dedup raw item
            if await dedup.is_raw_item_duplicate(content_hash):
                logger.debug("Skipping duplicate raw item: %s", item.url)
                continue

            # 4. Store raw item
            raw_item_id = await self._store_raw_item(
                item, source_id, content_hash, db
            )
            await dedup.mark_raw_item(content_hash)
            new_count += 1

            # 5. Match rules and create alerts (capped per source)
            if matched_count >= MAX_ALERTS_PER_SOURCE:
                continue  # already hit limit for this source
            alerts_created = await self._match_and_alert(
                item, raw_item_id, content_hash, source, db, dedup
            )
            matched_count += alerts_created

        await db.commit()

        # 7. Update source status
        await self._update_source_success(db, source, new_count)
        await db.commit()

        # 8. Fetch log
        await self._store_fetch_log(
            db,
            source_id=source_id,
            status="success",
            items_fetched=len(raw_items),
            items_matched=matched_count,
            error_msg=None,
            started_at=started_at,
        )
        await db.commit()

        logger.info(
            "Source %s done — fetched=%d, new=%d, alerts=%d",
            source_name,
            len(raw_items),
            new_count,
            matched_count,
        )

    # ------------------------------------------------------------------
    # Item storage
    # ------------------------------------------------------------------

    async def _store_raw_item(
        self,
        item: RawItem,
        source_id: Any,
        content_hash: str,
        db,
    ) -> str:
        """Insert a raw item and return its UUID (as string)."""
        item_id = str(uuid.uuid4())
        await db.execute(
            text(
                "INSERT INTO raw_items "
                "  (id, source_id, content_hash, title, url, "
                "   content_text, published_at, metadata_, created_at) "
                "VALUES "
                "  (:id, :source_id, :hash, :title, :url, "
                "   :content, :pub, CAST(:meta AS jsonb), :now)"
            ),
            {
                "id": item_id,
                "source_id": source_id,
                "hash": content_hash,
                "title": item.title[:2000] if item.title else "",
                "url": item.url[:2000] if item.url else "",
                "content": item.content_text,
                "pub": _ensure_datetime(item.published_at) if item.published_at else None,
                "meta": json.dumps(item.metadata or {}, default=str),
                "now": datetime.now(timezone.utc),
            },
        )
        return item_id

    # ------------------------------------------------------------------
    # Rule matching and alert creation
    # ------------------------------------------------------------------

    async def _match_and_alert(
        self,
        item: RawItem,
        raw_item_id: str,
        content_hash: str,
        source: dict[str, Any],
        db,
        dedup: DedupChecker,
    ) -> int:
        """Run rules against *item*.  Returns the number of alerts created."""
        if not self._rules:
            return 0

        if self._use_rule_engine:
            return await self._match_and_alert_engine(
                item, raw_item_id, content_hash, source, db, dedup,
            )
        return await self._match_and_alert_fallback(
            item, raw_item_id, content_hash, source, db, dedup,
        )

    async def _match_and_alert_engine(
        self,
        item: RawItem,
        raw_item_id: str,
        content_hash: str,
        source: dict[str, Any],
        db,
        dedup: DedupChecker,
    ) -> int:
        """Rule-engine path: use typed Rule objects and proper matcher API."""
        match_results = _re_match_rules(
            item.title or "",
            item.content_text or "",
            self._rules,
        )
        if not match_results:
            logger.info(
                "  No rule matches for: %s",
                (item.title or "")[:80],
            )
            return 0

        # Filter out low-quality matches by minimum score threshold.
        # Score of 0.10 means at least ~1 compound keyword on a 10-keyword rule.
        # Compound keywords (e.g. "gold price", "قیمت طلا") are specific enough
        # that even a single match indicates relevance.
        top = match_results[0]
        match_results = [
            mr for mr in match_results
            if mr.match_score >= MIN_MATCH_SCORE
        ]
        if not match_results:
            logger.info(
                "  Best score %.3f (kw=%d sig=%d) < threshold for: %s (rule=%s, kw=%s)",
                top.match_score,
                len(top.matched_keywords),
                len(top.matched_signals),
                (item.title or "")[:60],
                top.rule.id,
                top.matched_keywords[:3],
            )
            return 0

        best_score = match_results[0].match_score

        # LLM relevance filter for borderline matches (score < HIGH_CONFIDENCE_SCORE).
        # High-confidence matches (>= 0.30) skip this check.
        # This catches false positives like sports articles mentioning "gold".
        if best_score < HIGH_CONFIDENCE_SCORE:
            llm_enabled = await self._check_llm_enabled(db)
            if llm_enabled and settings.OPENROUTER_API_KEY:
                try:
                    is_relevant = await self._llm_relevance_check(
                        item.title or "", item.content_text or "", db=db,
                    )
                    if not is_relevant:
                        logger.info(
                            "  LLM says NOT relevant (score=%.3f): %s",
                            best_score,
                            (item.title or "")[:60],
                        )
                        return 0
                except Exception:
                    logger.debug(
                        "LLM relevance check failed, proceeding with alert",
                        exc_info=True,
                    )

        logger.info(
            "  MATCH score=%.3f rules=%d for: %s",
            best_score,
            len(match_results),
            (item.title or "")[:80],
        )

        # Build a single combined alert from all matched rules
        raw_item_dict = {
            "title": item.title or "",
            "content": item.content_text or "",
            "source_name": source.get("name", ""),
            "source_url": item.url or "",
            "url": item.url or "",
        }

        alert = _re_build_alert(raw_item_dict, match_results)
        alert["raw_item_id"] = raw_item_id

        # Persist direction data and news type in match_evidence for the API to read
        evidence = alert.get("match_evidence", {})
        evidence["direction"] = alert.get("direction", "neutral")
        evidence["direction_confidence"] = alert.get("direction_confidence", 0.0)
        evidence["direction_method"] = alert.get("direction_method", "fallback")
        evidence["alert_score"] = alert.get("alert_score", 50)
        evidence["news_type"] = alert.get("news_type", "causal_event")
        alert["match_evidence"] = evidence

        dedupe_key = alert["dedupe_key"]

        if await dedup.is_alert_duplicate(dedupe_key):
            logger.debug("Skipping duplicate alert: %s", dedupe_key)
            return 0

        # Semantic event dedup — catches same event with different headlines
        if await dedup.is_event_duplicate(
            item.title or "", item.content_text or "",
        ):
            logger.info(
                "  Skipping semantically duplicate event: %s",
                (item.title or "")[:60],
            )
            return 0

        # Optional LLM enrichment
        llm_enabled = await self._check_llm_enabled(db)
        if llm_enabled and settings.OPENROUTER_API_KEY:
            try:
                llm_result = await self._call_llm(
                    item.title, item.content_text, db=db,
                )
                if llm_result.get("title_fa"):
                    alert["title"] = llm_result["title_fa"]
                if llm_result.get("summary_fa"):
                    alert["summary_fa"] = llm_result["summary_fa"]
                if llm_result.get("why_important_fa"):
                    alert["why_important_fa"] = llm_result["why_important_fa"]
            except Exception:
                logger.warning(
                    "LLM enrichment failed for item %s",
                    item.url,
                    exc_info=True,
                )

        await self._store_alert(db, alert)
        await dedup.mark_alert(dedupe_key)
        await dedup.mark_event(item.title or "", item.content_text or "")
        return 1

    async def _match_and_alert_fallback(
        self,
        item: RawItem,
        raw_item_id: str,
        content_hash: str,
        source: dict[str, Any],
        db,
        dedup: DedupChecker,
    ) -> int:
        """Fallback path: dict-based rules with simple keyword matching."""
        matched_rules = _fallback_match_rules(item, self._rules)
        if not matched_rules:
            return 0

        logger.debug(
            "Item %s matched %d rule(s) (fallback)", item.url, len(matched_rules),
        )

        llm_enabled = await self._check_llm_enabled(db)
        alerts_created = 0

        for rule in matched_rules:
            severity = _fallback_determine_severity(rule)
            alert = _fallback_build_alert(rule, item, severity, raw_item_id)
            dedupe_key = alert.get(
                "dedupe_key",
                f"{rule.get('id', 'unknown')}:{content_hash}",
            )
            alert["dedupe_key"] = dedupe_key

            if await dedup.is_alert_duplicate(dedupe_key):
                logger.debug("Skipping duplicate alert: %s", dedupe_key)
                continue

            if llm_enabled and settings.OPENROUTER_API_KEY:
                try:
                    llm_result = await self._call_llm(
                        item.title, item.content_text, db=db,
                    )
                    if llm_result.get("title_fa"):
                        alert["title"] = llm_result["title_fa"]
                    if llm_result.get("summary_fa"):
                        alert["summary_fa"] = llm_result["summary_fa"]
                    if llm_result.get("why_important_fa"):
                        alert["why_important_fa"] = llm_result["why_important_fa"]
                except Exception:
                    logger.warning(
                        "LLM enrichment failed for item %s",
                        item.url,
                        exc_info=True,
                    )

            await self._store_alert(db, alert)
            await dedup.mark_alert(dedupe_key)
            alerts_created += 1

        return alerts_created

    async def _store_alert(self, db, alert: dict[str, Any]) -> None:
        alert_id = alert.get("id", str(uuid.uuid4()))
        await db.execute(
            text(
                "INSERT INTO alerts "
                "  (id, title, timestamp_utc, source_name, source_url, "
                "   matched_rule_ids, summary_fa, why_important_fa, "
                "   expected_impact, severity, time_horizon, confidence, "
                "   follow_up_questions, dedupe_key, raw_item_id, "
                "   match_evidence, created_at) "
                "VALUES "
                "  (:id, :title, :ts, :source_name, :source_url, "
                "   CAST(:rule_ids AS jsonb), :summary_fa, :why_important_fa, "
                "   CAST(:impact AS jsonb), :severity, :time_horizon, :confidence, "
                "   CAST(:questions AS jsonb), :dedupe_key, :raw_item_id, "
                "   CAST(:evidence AS jsonb), :now)"
            ),
            {
                "id": alert_id,
                "title": alert.get("title", ""),
                "ts": _ensure_datetime(alert.get("timestamp_utc")),
                "source_name": alert.get("source_name", ""),
                "source_url": alert.get("source_url", ""),
                "rule_ids": json.dumps(alert.get("matched_rule_ids", []), default=str),
                "summary_fa": _ensure_str(alert.get("summary_fa", "")),
                "why_important_fa": _ensure_str(alert.get("why_important_fa", "")),
                "impact": json.dumps(alert.get("expected_impact", {}), default=str),
                "severity": alert.get("severity", "medium"),
                "time_horizon": alert.get("time_horizon", "short"),
                "confidence": alert.get("confidence", 0.5),
                "questions": json.dumps(alert.get("follow_up_questions", []), default=str),
                "dedupe_key": alert.get("dedupe_key", ""),
                "raw_item_id": alert.get("raw_item_id"),
                "evidence": json.dumps(alert.get("match_evidence", {}), default=str),
                "now": datetime.now(timezone.utc),
            },
        )

    # ------------------------------------------------------------------
    # LLM integration (OpenRouter)
    # ------------------------------------------------------------------

    async def _check_llm_enabled(self, db) -> bool:
        """Read ``llm_enabled`` flag from the settings table."""
        try:
            result = await db.execute(
                text(
                    "SELECT value FROM settings "
                    "WHERE key = 'enable_llm' LIMIT 1"
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return str(row).lower() in ("true", "1", "yes")
        except Exception:
            logger.debug(
                "Could not read llm_enabled from settings", exc_info=True
            )
        return False

    async def _llm_relevance_check(
        self, title: str, content: str, db=None,
    ) -> bool:
        """Quick LLM check: is this article relevant to gold/financial markets?

        Uses a minimal prompt (~100 tokens) to verify borderline matches.
        Returns True if relevant, True on any error (fail-open).
        """
        text = title
        if content:
            text += "\n" + content[:500]

        model = await self._get_llm_model(db) if db else "anthropic/claude-sonnet-4"

        prompt = (
            "Is this news article relevant to ANY of these topics? "
            "Gold/precious metals, currency/forex, interest rates, "
            "central bank policy, economic data, geopolitics affecting markets, "
            "Iranian economy, stock market crisis.\n\n"
            f"Article: {text[:600]}\n\n"
            "Reply with ONLY 'YES' or 'NO'."
        )

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 5,
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with self._http_session.post(  # type: ignore[union-attr]
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

            reply = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
                .upper()
            )
            is_relevant = reply.startswith("YES")
            logger.debug(
                "LLM relevance check: %s → %s",
                title[:60] if title else "?",
                "YES" if is_relevant else "NO",
            )
            return is_relevant
        except Exception:
            logger.debug("LLM relevance check failed, assuming relevant", exc_info=True)
            return True  # Fail-open: let it through on error

    async def _get_llm_model(self, db) -> str:
        """Read the configured LLM model from settings, with fallback."""
        try:
            result = await db.execute(
                text("SELECT value FROM settings WHERE key = 'openrouter_model' LIMIT 1")
            )
            row = result.scalar_one_or_none()
            if row and isinstance(row, str):
                cleaned = row.strip().strip('"')
                if cleaned:
                    return cleaned
        except Exception:
            pass
        return "anthropic/claude-sonnet-4"

    async def _call_llm(
        self, title: str, content: str, db=None,
    ) -> dict[str, str | None]:
        """Call OpenRouter to generate Persian title, summary, and importance note."""
        model = await self._get_llm_model(db) if db else "anthropic/claude-sonnet-4"

        prompt = (
            "You are a Persian-language gold-market analyst. Given the following news "
            "item, generate text in Persian (فارسی). Respond ONLY with a valid JSON object.\n\n"
            "Required JSON keys:\n"
            '- "title_fa": A short Persian headline (max 80 chars) capturing the main point\n'
            '- "summary_fa": A concise summary in Persian (2-3 sentences)\n'
            '- "why_important_fa": Why this matters for the gold market in Persian (2-3 bullet points with "- " prefix)\n\n'
            f"Title: {title}\n\n"
            f"Content: {content[:3000]}\n\n"
            "Respond with ONLY the JSON object. No extra text."
        )

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        async with self._http_session.post(  # type: ignore[union-attr]
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        reply = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        # Strip markdown fences if present
        text_content = reply.strip()
        if text_content.startswith("```"):
            first_nl = text_content.find("\n")
            if first_nl != -1:
                text_content = text_content[first_nl + 1:]
            if text_content.endswith("```"):
                text_content = text_content[:-3]
            text_content = text_content.strip()

        # Try to parse as JSON; fall back to raw text.
        try:
            parsed = json.loads(text_content)
            # Ensure text fields are strings (LLM sometimes returns lists)
            why_fa = parsed.get("why_important_fa")
            if isinstance(why_fa, list):
                why_fa = "\n".join(str(x) for x in why_fa)
            summary_fa = parsed.get("summary_fa")
            if isinstance(summary_fa, list):
                summary_fa = "\n".join(str(x) for x in summary_fa)
            return {
                "title_fa": parsed.get("title_fa"),
                "summary_fa": summary_fa,
                "why_important_fa": why_fa,
            }
        except (json.JSONDecodeError, TypeError):
            return {"title_fa": None, "summary_fa": reply, "why_important_fa": None}

    # ------------------------------------------------------------------
    # Source status updates
    # ------------------------------------------------------------------

    async def _update_source_success(
        self, db, source: dict[str, Any], items_count: int
    ) -> None:
        now = datetime.now(timezone.utc)
        await db.execute(
            text(
                "UPDATE sources "
                "SET last_fetched_at = :now, "
                "    last_success_at = :now, "
                "    last_error = NULL "
                "WHERE id = :id"
            ),
            {"now": now, "id": source["id"]},
        )

    async def _record_source_error(
        self,
        db,
        source: dict[str, Any],
        error_msg: str = "unknown error",
    ) -> None:
        now = datetime.now(timezone.utc)
        try:
            await db.execute(
                text(
                    "UPDATE sources "
                    "SET last_fetched_at = :now, "
                    "    last_error = :err "
                    "WHERE id = :id"
                ),
                {"now": now, "err": error_msg[:2000], "id": source["id"]},
            )
            await db.commit()

            await self._store_fetch_log(
                db,
                source_id=source["id"],
                status="error",
                items_fetched=0,
                items_matched=0,
                error_msg=error_msg[:2000],
                started_at=now,
            )
            await db.commit()
        except Exception:
            logger.warning(
                "Failed to record error for source %s",
                source.get("id"),
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Fetch log
    # ------------------------------------------------------------------

    async def _store_fetch_log(
        self,
        db,
        *,
        source_id: Any,
        status: str,
        items_fetched: int,
        items_matched: int,
        error_msg: str | None,
        started_at: datetime,
    ) -> None:
        log_id = str(uuid.uuid4())
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        try:
            await db.execute(
                text(
                    "INSERT INTO fetch_logs "
                    "  (id, source_id, started_at, finished_at, status, "
                    "   items_fetched_count, error_message, duration_ms) "
                    "VALUES "
                    "  (:id, :src, :started, :finished, :status, "
                    "   :fetched, :err, :duration)"
                ),
                {
                    "id": log_id,
                    "src": source_id,
                    "started": started_at,
                    "finished": finished_at,
                    "status": status,
                    "fetched": items_fetched,
                    "err": error_msg,
                    "duration": duration_ms,
                },
            )
        except Exception:
            logger.warning(
                "Failed to store fetch log for source %s",
                source_id,
                exc_info=True,
            )


# ===================================================================
# Built-in fallback rule matching (used when rule_engine is absent)
# ===================================================================

def _fallback_match_rules(
    item: RawItem, rules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Simple keyword-in-text matching."""
    text_lower = f"{item.title} {item.content_text}".lower()
    matched: list[dict[str, Any]] = []
    for rule in rules:
        keywords: list[str] = rule.get("keywords", [])
        if not keywords:
            continue
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(rule)
    return matched


def _fallback_determine_severity(rule: dict[str, Any]) -> str:
    return rule.get("severity", "medium")


def _fallback_build_alert(
    rule: dict[str, Any],
    item: RawItem,
    severity: str,
    raw_item_id: str,
) -> dict[str, Any]:
    rule_id = rule.get("id", "unknown")
    return {
        "id": str(uuid.uuid4()),
        "raw_item_id": raw_item_id,
        "matched_rule_ids": [rule_id],
        "severity": severity,
        "time_horizon": rule.get("horizon", "short"),
        "confidence": 0.5,
        "dedupe_key": f"{rule_id}:{item.url}",
        "title": item.title or "",
        "source_name": "",
        "source_url": item.url or "",
        "summary_fa": (item.content_text or "")[:200],
        "why_important_fa": rule.get("why_important", ""),
        "expected_impact": [],
        "follow_up_questions": [],
        "match_evidence": {},
    }


# ===================================================================
# Utility helpers
# ===================================================================

def _load_rules(yaml_path: str) -> list[dict[str, Any]]:
    """Load rules from a YAML file.  Returns an empty list on failure."""
    path = Path(yaml_path)
    if not path.exists():
        logger.warning("Rules file not found: %s", path)
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        rules = data.get("rules", []) if isinstance(data, dict) else []
        logger.info("Loaded %d rules from %s", len(rules), path)
        return rules
    except Exception:
        logger.exception("Failed to load rules from %s", path)
        return []


def _ensure_str(value: Any) -> str:
    """Coerce *value* to a string. Lists are joined with newlines."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(x) for x in value)
    return str(value) if value is not None else ""


def _ensure_datetime(value: Any) -> datetime:
    """Convert *value* to a ``datetime`` object.

    asyncpg requires native datetime objects for ``timestamptz`` columns — it
    does not accept ISO-format strings.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


def _compute_content_hash(item: RawItem) -> str:
    """SHA-256 hash of the item's core content for deduplication."""
    payload = f"{item.title}|{item.url}|{item.content_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _format_exc() -> str:
    """Return a short traceback string for the current exception."""
    import traceback

    return traceback.format_exc(limit=5)[-2000:]


# ===================================================================
# Entry point
# ===================================================================

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Quieten noisy libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    worker = Worker()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")


if __name__ == "__main__":
    main()
