"""ORM models for the data reliability & provenance module.

Tables
------
- ``metric_definitions``   — metric data cards (seed data)
- ``metric_runs``          — one row per metric computation run
- ``raw_ingests``          — raw API response log per external fetch
- ``transform_steps``      — per-step computation log
- ``validation_results``   — QA check results per run
- ``metric_alerts``        — alerts for failed/stale metrics
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from api.models import Base


class MetricDefinition(Base):
    """Metric data card — describes what a metric is and how it's computed."""

    __tablename__ = "metric_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id = Column(String(64), unique=True, nullable=False)
    display_name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    unit = Column(String(32), nullable=True)
    timezone = Column(String(32), nullable=False, default="UTC")
    update_frequency_minutes = Column(Integer, nullable=True)
    formula_version = Column(String(16), nullable=False, default="v1")
    raw_sources = Column(JSONB, nullable=True)
    formula_steps = Column(JSONB, nullable=True)
    dependencies = Column(JSONB, nullable=True)
    expected_range = Column(JSONB, nullable=True)
    sanity_rules = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class MetricRun(Base):
    """One row per metric computation run."""

    __tablename__ = "metric_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id = Column(String(64), ForeignKey("metric_definitions.metric_id"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="running")
    qa_result = Column(String(16), nullable=True)
    qa_reasons = Column(JSONB, nullable=True)
    final_value = Column(JSONB, nullable=True)
    data_timestamp = Column(DateTime(timezone=True), nullable=True)
    formula_version = Column(String(16), nullable=True)
    fallback_used = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Index created by migration 013 (metric_id, started_at DESC)


class RawIngest(Base):
    """Raw API response log — one per external fetch in a run."""

    __tablename__ = "raw_ingests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("metric_runs.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(String(64), nullable=False)
    request_url = Column(Text, nullable=True)
    request_params = Column(JSONB, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_size_bytes = Column(Integer, nullable=True)
    payload_hash = Column(String(64), nullable=True)
    payload_sample = Column(JSONB, nullable=True)
    data_timestamp_in_payload = Column(DateTime(timezone=True), nullable=True)
    retrieved_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    latency_ms = Column(Integer, nullable=True)

    # Indexes created by migration 013


class TransformStep(Base):
    """One computation step within a metric run."""

    __tablename__ = "transform_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("metric_runs.id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, nullable=False)
    step_name = Column(String(64), nullable=False)
    input_refs = Column(JSONB, nullable=True)
    output_value = Column(JSONB, nullable=True)
    normalization_method = Column(String(32), nullable=True)
    normalization_params = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Index created by migration 013


class ValidationResult(Base):
    """One QA check result within a metric run."""

    __tablename__ = "validation_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("metric_runs.id", ondelete="CASCADE"), nullable=False)
    check_name = Column(String(64), nullable=False)
    result = Column(String(16), nullable=False)
    reason = Column(Text, nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Index created by migration 013


class MetricAlert(Base):
    """Alert entry for failed or stale metrics."""

    __tablename__ = "metric_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id = Column(String(64), nullable=False)
    alert_type = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False)
    message = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Indexes created by migration 013 (including partial index on resolved_at)
