"""SQL query safety guard for the workbench.

Validates and sanitises arbitrary SQL before execution:
- Only SELECT / WITH...SELECT allowed
- Blocked keywords (INSERT, UPDATE, DELETE, DROP, etc.)
- Blocked tables (admin_users, chat_settings)
- Row limit cap (100)
- Statement timeout (10s)
- Read-only transaction
- Value truncation for long text
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "SET", "EXECUTE", "GRANT", "REVOKE", "COPY",
    "DO", "CALL", "NOTIFY", "LISTEN", "VACUUM", "REINDEX",
    "CLUSTER", "COMMENT", "SECURITY", "LOCK",
}

BLOCKED_PATTERNS = [
    r"\bINTO\b",      # SELECT INTO
    r"\bpg_\w+",      # pg_ functions
    r"--",             # SQL comments
    r"/\*",            # Block comments
    r"\\",             # Backslash escapes
]

BLOCKED_TABLES = {"admin_users", "chat_settings"}

MAX_ROWS = 100
STATEMENT_TIMEOUT_MS = 10_000
MAX_TEXT_LEN = 200


class SQLGuardError(Exception):
    """Raised when a query fails safety checks."""


def validate_query(query: str) -> str:
    """Validate and normalise a SQL query. Returns cleaned query or raises SQLGuardError."""
    if not query or not query.strip():
        raise SQLGuardError("کوئری خالی است.")

    cleaned = query.strip().rstrip(";")
    upper = cleaned.upper()

    # Must start with SELECT or WITH
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise SQLGuardError("فقط کوئری‌های SELECT و WITH...SELECT مجاز هستند.")

    # Check blocked keywords (word boundaries)
    for kw in BLOCKED_KEYWORDS:
        pattern = rf"\b{kw}\b"
        if re.search(pattern, upper):
            raise SQLGuardError(f"کلیدواژه '{kw}' در کوئری مجاز نیست.")

    # Check blocked patterns
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, upper):
            raise SQLGuardError("الگوی غیرمجاز در کوئری شناسایی شد.")

    # Check blocked tables
    lower = cleaned.lower()
    for table in BLOCKED_TABLES:
        if table in lower:
            raise SQLGuardError(f"دسترسی به جدول '{table}' مجاز نیست.")

    # Append LIMIT if missing
    if "LIMIT" not in upper:
        cleaned += f" LIMIT {MAX_ROWS}"
    else:
        # Extract existing limit and cap it
        limit_match = re.search(r"\bLIMIT\s+(\d+)", upper)
        if limit_match:
            existing_limit = int(limit_match.group(1))
            if existing_limit > MAX_ROWS:
                cleaned = re.sub(
                    r"\bLIMIT\s+\d+",
                    f"LIMIT {MAX_ROWS}",
                    cleaned,
                    flags=re.IGNORECASE,
                )

    return cleaned


def _truncate_value(val: Any) -> Any:
    """Truncate long string values for display."""
    if isinstance(val, str) and len(val) > MAX_TEXT_LEN:
        return val[:MAX_TEXT_LEN] + "..."
    return val


async def execute_safe_query(
    db: AsyncSession,
    query: str,
) -> dict[str, Any]:
    """Execute a validated read-only SQL query and return results."""
    cleaned = validate_query(query)

    try:
        # Set read-only + timeout
        await db.execute(text("SET TRANSACTION READ ONLY"))
        await db.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}'"))

        result = await db.execute(text(cleaned))
        rows = result.fetchall()
        columns = list(result.keys()) if result.keys() else []

        # Format results
        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                row_dict[col] = _truncate_value(row[i])
            data.append(row_dict)

        return {
            "columns": columns,
            "rows": data,
            "row_count": len(data),
            "query": cleaned,
        }

    except SQLGuardError:
        raise
    except Exception as e:
        error_msg = str(e)
        # Sanitise error - don't expose internal details
        if "statement timeout" in error_msg.lower():
            raise SQLGuardError("کوئری بیش از ۱۰ ثانیه طول کشید و متوقف شد.")
        logger.warning("SQL execution error: %s", error_msg)
        raise SQLGuardError("خطا در اجرای کوئری. لطفاً ساختار کوئری را بررسی کنید.")
