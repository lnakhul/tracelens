"""SQLAlchemy models for TraceLens persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all TraceLens database models."""


class Trace(Base):
    """One proxied HTTP exchange captured by TraceLens."""

    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String, index=True)
    query_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, index=True)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)


class FailureAnalysisAudit(Base):
    """Metadata-only record of an AI analysis attempt."""

    __tablename__ = "failure_analysis_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    trace_id: Mapped[int] = mapped_column(Integer, index=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    include_bodies: Mapped[bool] = mapped_column(Boolean)
    outcome: Mapped[str] = mapped_column(String(32))
    provider_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer)