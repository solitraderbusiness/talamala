"""ORM model for sentiment calculation audit logs.

Each run of ``compute_sentiment()`` persists a detailed log row so admins
can inspect exactly what raw data was used, how scores were derived, and
whether any component was stale or fell back to defaults.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from api.database import Base


class SentimentCalcLog(Base):
    """One row per sentiment gauge calculation run."""

    __tablename__ = "sentiment_calc_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Overall result
    overall_score = Column(Integer, nullable=True)
    overall_label = Column(String(20), nullable=True)
    overall_label_fa = Column(String(50), nullable=True)

    # Per-component details — JSON array of dicts, one per component.
    # Each dict contains:
    #   component_key, raw_value, raw_units, raw_transform,
    #   data_source_id, fetched_at, window_start, window_end, window_size,
    #   winsorization_applied, winsorize_bounds, smoothing_applied,
    #   smoothing_params, percentile_p, direction, final_score,
    #   crowded_flag, stale, fallback_used
    components = Column(JSON, nullable=False, default=list)

    # Warnings/errors (e.g. missing data, stale components)
    warnings = Column(JSON, nullable=True)

    # Optional: app version or git hash for traceability
    app_version = Column(String(100), nullable=True)
