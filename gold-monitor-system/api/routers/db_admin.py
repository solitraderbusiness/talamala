"""Admin API endpoints for database intelligence.

Provides schema exploration, table health, data freshness, and row counts.
Mounted at ``/api/admin/database``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from api.database import AsyncSessionLocal
from api.routers.admin import get_current_admin

router = APIRouter(tags=["database"], dependencies=[Depends(get_current_admin)])
logger = logging.getLogger("db_admin")

# Tables grouped by module for the UI
TABLE_MODULES = {
    "sources": "core",
    "raw_items": "core",
    "alerts": "core",
    "alert_price_outcomes": "core",
    "fetch_logs": "core",
    "settings": "core",
    "admin_users": "core",
    "sentiment_scores": "core",
    "economic_events": "core",
    "rules_snapshot": "core",
    "system_jobs": "core",
    "job_runs": "core",
    "chat_sessions": "core",
    "chat_messages": "core",
    "chat_analytics": "core",
    "chat_settings": "core",
    "audit_logs": "core",
    "signal_sources": "signal",
    "raw_posts": "signal",
    "parsed_signals": "signal",
    "consensus_snapshots": "signal",
    "signal_price_ticks": "signal",
    "signal_daily_performance": "signal",
    "signal_monthly_performance": "signal",
    "signal_journal": "signal",
    "asset_prices_daily": "analysis",
    "macro_indicators": "analysis",
    "etf_holdings": "analysis",
    "cot_data": "analysis",
    "market_events_analysis": "analysis",
    "correlation_cache": "analysis",
    "regime_scores": "analysis",
    "backtest_runs": "analysis",
    "alert_market_snapshots": "data_collection",
    "alert_outcomes": "data_collection",
    "sentiment_timeline": "data_collection",
    "price_history": "data_collection",
    "metric_definitions": "data_reliability",
    "metric_runs": "data_reliability",
    "raw_ingests": "data_reliability",
    "transform_steps": "data_reliability",
    "validation_results": "data_reliability",
    "metric_alerts": "data_reliability",
    "gold_articles": "articles",
    "curated_videos": "videos",
    "live_stream_channels": "videos",
    "monitored_youtube_channels": "videos",
    "video_chat_logs": "videos",
}

MODULE_LABELS = {
    "core": "هسته سیستم",
    "signal": "سیگنال",
    "analysis": "تحلیل بنیادی",
    "data_collection": "جمع‌آوری داده",
    "data_reliability": "اعتبار داده",
    "articles": "مقالات",
    "videos": "ویدیوها",
}


@router.get("/schema")
async def schema_overview():
    """List all tables with column count, row count, and estimated size."""
    async with AsyncSessionLocal() as session:
        # Get all tables with row estimates and size
        q = await session.execute(text("""
            SELECT
                t.tablename,
                (SELECT COUNT(*) FROM information_schema.columns c
                 WHERE c.table_schema = 'public' AND c.table_name = t.tablename) as col_count,
                COALESCE(s.n_live_tup, 0) as row_estimate,
                pg_total_relation_size(quote_ident(t.tablename)::regclass) as total_bytes
            FROM pg_tables t
            LEFT JOIN pg_stat_user_tables s ON s.relname = t.tablename
            WHERE t.schemaname = 'public'
              AND t.tablename != 'alembic_version'
            ORDER BY t.tablename
        """))

        tables = []
        total_size = 0
        total_rows = 0
        for row in q.all():
            table_name = row[0]
            size_bytes = row[3] or 0
            row_count = row[2] or 0
            total_size += size_bytes
            total_rows += row_count
            tables.append({
                "name": table_name,
                "columns": row[1],
                "rows": row_count,
                "size_bytes": size_bytes,
                "size_human": _human_size(size_bytes),
                "module": TABLE_MODULES.get(table_name, "unknown"),
            })

        return {
            "tables": tables,
            "total_tables": len(tables),
            "total_rows": total_rows,
            "total_size_bytes": total_size,
            "total_size_human": _human_size(total_size),
            "modules": MODULE_LABELS,
        }


@router.get("/tables/{table_name}")
async def table_detail(table_name: str):
    """Detailed column info, null ratios, and sample data for a table."""
    # Validate table name to prevent SQL injection
    async with AsyncSessionLocal() as session:
        # Check table exists
        exists_q = await session.execute(text(
            "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = :t"
        ), {"t": table_name})
        if not exists_q.scalar():
            return {"error": "Table not found"}

        # Column details
        cols_q = await session.execute(text("""
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                c.character_maximum_length
            FROM information_schema.columns c
            WHERE c.table_schema = 'public' AND c.table_name = :t
            ORDER BY c.ordinal_position
        """), {"t": table_name})
        columns = [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3],
                "max_length": row[4],
            }
            for row in cols_q.all()
        ]

        # Row count
        count_q = await session.execute(text(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ))
        row_count = count_q.scalar() or 0

        # Null ratios for each column (sample-based for large tables)
        null_ratios = {}
        if row_count > 0:
            sample_limit = min(row_count, 10000)
            for col in columns:
                col_name = col["name"]
                try:
                    nr_q = await session.execute(text(
                        f'SELECT COUNT(*) FILTER (WHERE "{col_name}" IS NULL) * 100.0 / COUNT(*) '
                        f'FROM (SELECT "{col_name}" FROM "{table_name}" LIMIT :lim) sub'
                    ), {"lim": sample_limit})
                    ratio = nr_q.scalar()
                    null_ratios[col_name] = round(ratio, 1) if ratio is not None else None
                except Exception:
                    null_ratios[col_name] = None

        # Indexes
        idx_q = await session.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = :t AND schemaname = 'public'
        """), {"t": table_name})
        indexes = [{"name": row[0], "definition": row[1]} for row in idx_q.all()]

        # Data freshness (if table has created_at or timestamp column)
        freshness = None
        ts_col = None
        for col in columns:
            if col["name"] in ("created_at", "timestamp_utc", "started_at", "ts", "updated_at"):
                ts_col = col["name"]
                break
        if ts_col and row_count > 0:
            try:
                fresh_q = await session.execute(text(
                    f'SELECT MIN("{ts_col}"), MAX("{ts_col}") FROM "{table_name}"'
                ))
                fresh_row = fresh_q.one()
                freshness = {
                    "column": ts_col,
                    "oldest": fresh_row[0].isoformat() if fresh_row[0] else None,
                    "newest": fresh_row[1].isoformat() if fresh_row[1] else None,
                }
            except Exception:
                pass

        # Table size
        size_q = await session.execute(text(
            f"SELECT pg_total_relation_size('{table_name}'::regclass)"
        ))
        size_bytes = size_q.scalar() or 0

        return {
            "name": table_name,
            "module": TABLE_MODULES.get(table_name, "unknown"),
            "row_count": row_count,
            "size_bytes": size_bytes,
            "size_human": _human_size(size_bytes),
            "columns": columns,
            "null_ratios": null_ratios,
            "indexes": indexes,
            "freshness": freshness,
        }


@router.get("/health")
async def table_health():
    """Quick health check across all tables: row counts, freshness, null issues."""
    async with AsyncSessionLocal() as session:
        # Tables with timestamps and their freshness
        health_items = []

        # Get row counts for key tables
        key_tables = [
            ("alerts", "timestamp_utc"),
            ("raw_items", "fetched_at"),
            ("sources", "last_fetched_at"),
            ("system_jobs", "last_run_at"),
            ("job_runs", "started_at"),
            ("asset_prices_daily", "date"),
            ("macro_indicators", "date"),
            ("etf_holdings", "date"),
            ("sentiment_timeline", "recorded_at"),
            ("metric_runs", "started_at"),
            ("audit_logs", "created_at"),
        ]

        for table, ts_col in key_tables:
            try:
                q = await session.execute(text(
                    f'SELECT COUNT(*), MAX("{ts_col}") FROM "{table}"'
                ))
                row = q.one()
                health_items.append({
                    "table": table,
                    "module": TABLE_MODULES.get(table, "unknown"),
                    "rows": row[0] or 0,
                    "latest": row[1].isoformat() if row[1] else None,
                    "ts_column": ts_col,
                })
            except Exception:
                health_items.append({
                    "table": table,
                    "module": TABLE_MODULES.get(table, "unknown"),
                    "rows": 0,
                    "latest": None,
                    "ts_column": ts_col,
                    "error": True,
                })

        return {"health": health_items}


@router.get("/size")
async def database_size():
    """Overall database size statistics."""
    async with AsyncSessionLocal() as session:
        # Total DB size
        db_size_q = await session.execute(text(
            "SELECT pg_database_size(current_database())"
        ))
        db_size = db_size_q.scalar() or 0

        # Top tables by size
        top_q = await session.execute(text("""
            SELECT
                t.tablename,
                pg_total_relation_size(quote_ident(t.tablename)::regclass) as total_bytes
            FROM pg_tables t
            WHERE t.schemaname = 'public' AND t.tablename != 'alembic_version'
            ORDER BY total_bytes DESC
            LIMIT 15
        """))

        return {
            "database_size_bytes": db_size,
            "database_size_human": _human_size(db_size),
            "top_tables": [
                {
                    "name": row[0],
                    "size_bytes": row[1],
                    "size_human": _human_size(row[1]),
                    "pct": round(row[1] / db_size * 100, 1) if db_size > 0 else 0,
                }
                for row in top_q.all()
            ],
        }


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
