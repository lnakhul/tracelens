"""Pydantic schemas for TraceLens management endpoints."""

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator


class HealthResponse(BaseModel):
    """Response returned when the local management API is ready."""

    status: str


class TraceSummaryResponse(BaseModel):
    """List-safe fields for a captured HTTP exchange."""

    id: int
    timestamp: datetime
    method: str
    path: str
    status_code: int | None
    duration_ms: float
    error_type: str | None
    baseline_duration_ms: float | None = None
    latency_increase_ratio: float | None = None
    is_anomaly: bool = False

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """Treat SQLite's timezone-naive datetimes as the UTC values we stored."""

        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class TraceListResponse(BaseModel):
    """Paginated traces in reverse chronological order."""

    items: list[TraceSummaryResponse]
    total: int
    limit: int
    offset: int


class TraceDetailResponse(TraceSummaryResponse):
    """Complete locally captured trace data."""

    query_string: str | None
    request_headers: str | None
    request_body: str | None
    response_headers: str | None
    response_body: str | None


class MetricsResponse(BaseModel):
    """Summary metrics over all locally retained traces."""

    request_count: int
    error_rate: float
    average_duration_ms: float
    p95_duration_ms: float
