"""Persistence service for captured HTTP traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from tracelens.database.models import FailureAnalysisAudit, Trace


@dataclass(frozen=True, slots=True)
class TraceData:
    """Normalized data captured for one proxied HTTP exchange."""

    timestamp: datetime
    method: str
    path: str
    query_string: str | None
    status_code: int | None
    duration_ms: float
    error_type: str | None
    request_headers: str
    request_body: str | None
    response_headers: str
    response_body: str | None


@dataclass(frozen=True, slots=True)
class TracePage:
    """A page of stored traces and the total result count."""

    items: list[Trace]
    total: int


@dataclass(frozen=True, slots=True)
class TraceMetrics:
    """Metrics calculated from all retained local traces."""

    request_count: int
    error_rate: float
    average_duration_ms: float
    p95_duration_ms: float


@dataclass(frozen=True, slots=True)
class FailureAnalysisAuditData:
    """Non-sensitive metadata recorded for one AI analysis action."""

    timestamp: datetime
    trace_id: int
    model: str | None
    include_bodies: bool
    outcome: str
    provider_status_code: int | None
    attempt_count: int


class TraceService:
    """Store captured exchanges independently of proxy request handling."""

    _MIN_BASELINE_SAMPLES = 5
    _ANOMALY_MULTIPLIER = 2.0

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        retention_hours: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._retention_hours = retention_hours

    async def record(self, trace_data: TraceData) -> None:
        """Persist a captured trace in its own short-lived database session."""

        async with self._session_factory() as session:
            session.add(Trace(**asdict(trace_data)))
            if self._retention_hours is not None:
                await self._purge_expired(session)
            await session.commit()

    async def record_analysis_audit(self, audit_data: FailureAnalysisAuditData) -> None:
        """Persist metadata for an analysis action without retaining its prompt or result."""

        async with self._session_factory() as session:
            session.add(FailureAnalysisAudit(**asdict(audit_data)))
            await session.commit()

    async def analysis_audits(self, trace_id: int) -> list[FailureAnalysisAudit]:
        """Return analysis audit metadata for one trace, newest first."""

        async with self._session_factory() as session:
            statement = (
                select(FailureAnalysisAudit)
                .where(FailureAnalysisAudit.trace_id == trace_id)
                .order_by(FailureAnalysisAudit.timestamp.desc(), FailureAnalysisAudit.id.desc())
            )
            return list((await session.scalars(statement)).all())

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        path: str | None = None,
        status_code: int | None = None,
        min_duration_ms: float | None = None,
        max_duration_ms: float | None = None,
    ) -> TracePage:
        """Return a filtered reverse-chronological page of trace summaries."""

        filters = self._filters(
            path=path,
            status_code=status_code,
            min_duration_ms=min_duration_ms,
            max_duration_ms=max_duration_ms,
        )
        async with self._session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(Trace).where(*filters))
            statement = (
                self._trace_with_anomaly_columns()
                .where(*filters)
                .order_by(Trace.timestamp.desc(), Trace.id.desc())
                .offset(offset)
                .limit(limit)
            )
            items = self._attach_anomaly_analysis((await session.execute(statement)).all())
        return TracePage(items=items, total=total or 0)

    async def get(self, trace_id: int) -> Trace | None:
        """Return one complete trace, if it exists."""

        async with self._session_factory() as session:
            statement = self._trace_with_anomaly_columns().where(Trace.id == trace_id)
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                return None
            return self._attach_anomaly_analysis([row])[0]

    async def successful_comparisons(self, trace: Trace, limit: int = 5) -> list[Trace]:
        """Return recent successful calls to the same endpoint for failure comparison."""

        async with self._session_factory() as session:
            statement = (
                select(Trace)
                .where(
                    Trace.method == trace.method,
                    Trace.path == trace.path,
                    Trace.status_code.is_not(None),
                    Trace.status_code < 500,
                    Trace.id != trace.id,
                )
                .order_by(Trace.timestamp.desc(), Trace.id.desc())
                .limit(limit)
            )
            return list((await session.scalars(statement)).all())

    async def metrics(self) -> TraceMetrics:
        """Calculate request, error-rate, latency average, and nearest-rank P95 metrics."""

        async with self._session_factory() as session:
            request_count, error_count, average_duration_ms = (
                await session.execute(
                    select(
                        func.count(Trace.id),
                        func.sum(
                            case(
                                (
                                    or_(Trace.status_code >= 500, Trace.error_type.is_not(None)),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        func.avg(Trace.duration_ms),
                    )
                )
            ).one()
            if not request_count:
                return TraceMetrics(0, 0.0, 0.0, 0.0)

            p95_index = max(0, (95 * request_count + 99) // 100 - 1)
            p95_duration_ms = await session.scalar(
                select(Trace.duration_ms)
                .order_by(Trace.duration_ms.asc(), Trace.id.asc())
                .offset(p95_index)
                .limit(1)
            )
        return TraceMetrics(
            request_count=request_count,
            error_rate=(error_count or 0) / request_count,
            average_duration_ms=average_duration_ms or 0.0,
            p95_duration_ms=p95_duration_ms or 0.0,
        )

    async def clear(self) -> None:
        """Delete all traces from local storage."""

        async with self._session_factory() as session:
            await session.execute(delete(FailureAnalysisAudit))
            await session.execute(delete(Trace))
            await session.commit()

    async def delete(self, trace_id: int) -> bool:
        """Delete one trace and all of its local analysis audit metadata."""

        async with self._session_factory() as session:
            result = await session.execute(delete(Trace).where(Trace.id == trace_id))
            if not result.rowcount:
                return False
            await session.execute(
                delete(FailureAnalysisAudit).where(FailureAnalysisAudit.trace_id == trace_id)
            )
            await session.commit()
            return True

    async def _purge_expired(self, session: AsyncSession) -> None:
        """Remove expired traces and their metadata-only analysis audits in one transaction."""

        if self._retention_hours is None:
            return
        cutoff = datetime.now(UTC) - timedelta(hours=self._retention_hours)
        expired_trace_ids = select(Trace.id).where(Trace.timestamp < cutoff)
        await session.execute(
            delete(FailureAnalysisAudit).where(FailureAnalysisAudit.trace_id.in_(expired_trace_ids))
        )
        await session.execute(delete(Trace).where(Trace.timestamp < cutoff))

    @staticmethod
    def _filters(
        *,
        path: str | None,
        status_code: int | None,
        min_duration_ms: float | None,
        max_duration_ms: float | None,
    ) -> list[object]:
        filters: list[object] = []
        if path:
            filters.append(Trace.path.contains(path))
        if status_code is not None:
            filters.append(Trace.status_code == status_code)
        if min_duration_ms is not None:
            filters.append(Trace.duration_ms >= min_duration_ms)
        if max_duration_ms is not None:
            filters.append(Trace.duration_ms <= max_duration_ms)
        return filters

    @staticmethod
    def _trace_with_anomaly_columns():
        """Select traces with correlated aggregates over earlier endpoint calls."""

        prior = aliased(Trace)
        earlier_trace = or_(
            prior.timestamp < Trace.timestamp,
            and_(prior.timestamp == Trace.timestamp, prior.id < Trace.id),
        )
        same_endpoint = and_(prior.method == Trace.method, prior.path == Trace.path)
        prior_count = (
            select(func.count(prior.id))
            .where(same_endpoint, earlier_trace)
            .correlate(Trace)
            .scalar_subquery()
        )
        prior_average = (
            select(func.avg(prior.duration_ms))
            .where(same_endpoint, earlier_trace)
            .correlate(Trace)
            .scalar_subquery()
        )
        return select(
            Trace,
            prior_count.label("prior_count"),
            prior_average.label("prior_average"),
        )

    @classmethod
    def _attach_anomaly_analysis(cls, rows: list[object]) -> list[Trace]:
        """Attach calculated latency fields to the bounded ORM result set."""

        traces: list[Trace] = []
        for trace, prior_count, prior_average in rows:
            baseline_duration_ms = (
                float(prior_average)
                if prior_count >= cls._MIN_BASELINE_SAMPLES and prior_average is not None
                else None
            )
            latency_increase_ratio = (
                trace.duration_ms / baseline_duration_ms
                if baseline_duration_ms and baseline_duration_ms > 0
                else None
            )
            trace.baseline_duration_ms = baseline_duration_ms
            trace.latency_increase_ratio = latency_increase_ratio
            trace.is_anomaly = (
                latency_increase_ratio is not None
                and latency_increase_ratio >= cls._ANOMALY_MULTIPLIER
            )
            traces.append(trace)
        return traces
