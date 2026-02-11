"""
Pydantic v2 schemas for request / response serialisation.

Persian-friendly field aliases are provided via ``Field(alias=...)``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Shared config ───────────────────────────────────────────────────────

class _CamelBase(BaseModel):
    """Base model that allows population by field name OR alias."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


# =====================================================================
#  Alerts
# =====================================================================

class AlertResponse(_CamelBase):
    id: uuid.UUID
    title: str = Field(..., alias="عنوان")
    timestamp_utc: datetime
    source_name: str = Field(..., alias="منبع")
    source_url: str
    matched_rule_ids: list[str] = Field(default_factory=list)
    summary_fa: str = Field("", alias="خلاصه")
    why_important_fa: str = Field("", alias="چرا_مهم")
    expected_impact: dict[str, Any] = Field(default_factory=dict, alias="تاثیر_مورد_انتظار")
    severity: str = Field(..., alias="شدت")
    time_horizon: str = Field(..., alias="افق_زمانی")
    confidence: float = Field(..., alias="اطمینان")
    follow_up_questions: list[str] = Field(default_factory=list)
    dedupe_key: str
    raw_item_id: uuid.UUID | None = None
    match_evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AlertListResponse(_CamelBase):
    total: int
    page: int
    page_size: int
    items: list[AlertResponse]


class AlertFilters(_CamelBase):
    severity: str | None = None
    time_horizon: str | None = None
    source_name: str | None = None
    rule_id: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    search: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# =====================================================================
#  Sources
# =====================================================================

class SourceCreate(_CamelBase):
    name: str
    type: str
    base_url: str
    endpoints: list[str] = Field(default_factory=list)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    parser: str | None = None
    enabled: bool = True
    poll_interval_seconds: int = 60
    categories: list[str] = Field(default_factory=list)
    rule_bindings: list[str] = Field(default_factory=list)
    reliability_score: float | None = None
    notes: str | None = None


class SourceUpdate(_CamelBase):
    name: str | None = None
    type: str | None = None
    base_url: str | None = None
    endpoints: list[str] | None = None
    method: str | None = None
    headers: dict[str, str] | None = None
    auth_config: dict[str, Any] | None = None
    parser: str | None = None
    enabled: bool | None = None
    poll_interval_seconds: int | None = None
    categories: list[str] | None = None
    rule_bindings: list[str] | None = None
    reliability_score: float | None = None
    notes: str | None = None


class SourceResponse(_CamelBase):
    id: uuid.UUID
    name: str
    type: str
    base_url: str
    endpoints: list[str] = Field(default_factory=list)
    method: str
    headers: dict[str, str] = Field(default_factory=dict)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    parser: str | None = None
    enabled: bool
    poll_interval_seconds: int
    categories: list[str] = Field(default_factory=list)
    rule_bindings: list[str] = Field(default_factory=list)
    reliability_score: float | None = None
    notes: str | None = None
    last_fetched_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceListResponse(_CamelBase):
    total: int
    items: list[SourceResponse]


# =====================================================================
#  Fetch Logs
# =====================================================================

class FetchLogResponse(_CamelBase):
    id: uuid.UUID
    source_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    items_fetched_count: int = 0
    error_message: str | None = None
    duration_ms: int | None = None


# =====================================================================
#  Settings
# =====================================================================

class SettingUpdate(_CamelBase):
    value: Any


class SettingResponse(_CamelBase):
    key: str
    value: Any
    updated_at: datetime


# =====================================================================
#  Auth
# =====================================================================

class LoginRequest(_CamelBase):
    email: str
    password: str


class TokenResponse(_CamelBase):
    access_token: str
    token_type: str = "bearer"


# =====================================================================
#  Stats / Dashboard
# =====================================================================

class TopAlert(_CamelBase):
    """Lightweight alert summary used in the stats endpoint."""

    id: uuid.UUID
    title: str = Field(..., alias="عنوان")
    severity: str = Field(..., alias="شدت")
    timestamp_utc: datetime
    source_name: str = Field(..., alias="منبع")


class StatsResponse(_CamelBase):
    total_alerts: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    risk_score: float = Field(..., alias="امتیاز_ریسک")
    top_alerts: list[TopAlert] = Field(default_factory=list)
    active_sources: int
    total_sources: int


# =====================================================================
#  Rules
# =====================================================================

class RuleResponse(_CamelBase):
    id: str
    title: str = Field(..., alias="عنوان")
    title_fa: str | None = Field(None, alias="عنوان_فارسی")
    category: str
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True


class RuleCategoryResponse(_CamelBase):
    category: str = Field(..., alias="دسته")
    rules: list[RuleResponse]


# =====================================================================
#  Health
# =====================================================================

class HealthResponse(_CamelBase):
    status: str
    database: str
    redis: str
    version: str
    uptime_seconds: float


# =====================================================================
#  Operations Monitoring
# =====================================================================

class SystemJobResponse(_CamelBase):
    id: uuid.UUID
    job_name: str
    job_label_fa: str | None = None
    job_category: str
    schedule: str | None = None
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None
    items_processed: int | None = 0
    status: str
    expected_interval_minutes: int
    enabled: bool
    success_rate_24h: float | None = None
    created_at: datetime
    updated_at: datetime


class JobRunResponse(_CamelBase):
    id: uuid.UUID
    job_id: uuid.UUID
    job_name: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    items_processed: int | None = 0
    error_message: str | None = None
    duration_ms: int | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MonitoringOverview(_CamelBase):
    jobs_healthy: int = 0
    jobs_warning: int = 0
    jobs_error: int = 0
    jobs_stale: int = 0
    total_jobs: int = 0
    total_runs_24h: int = 0
    success_rate_24h: float = 0.0
    last_check_at: datetime | None = None


class SystemHealthExternalResponse(_CamelBase):
    """Response for GET /api/admin/health — external monitoring."""

    status: str  # "healthy" | "degraded" | "down"
    jobs_healthy: int = 0
    jobs_warning: int = 0
    jobs_error: int = 0
    oldest_stale_job: str | None = None
    timestamp: datetime


class DataFreshnessResponse(_CamelBase):
    """Public endpoint for data freshness indicators."""

    last_news_fetch: datetime | None = None
    last_price_update: datetime | None = None
    last_sentiment_update: datetime | None = None
    last_worker_run: datetime | None = None
