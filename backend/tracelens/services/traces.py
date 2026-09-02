"""Persistence service for captured HTTP traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
                select(Trace)
                .where(*filters)
                .order_by(Trace.timestamp.desc(), Trace.id.desc())
                .offset(offset)
                .limit(limit)
            )
            items = list((await session.scalars(statement)).all())
            endpoint_keys = {(item.method, item.path) for item in items}
            if endpoint_keys:
                analysis_traces = list(
                    (
                        await session.scalars(
                            select(Trace)
                            .where(tuple_(Trace.method, Trace.path).in_(endpoint_keys))
                            .order_by(Trace.timestamp.asc(), Trace.id.asc())
                        )
                    ).all()
                )
                self._apply_anomaly_analysis(analysis_traces)
        return TracePage(items=items, total=total or 0)

    async def get(self, trace_id: int) -> Trace | None:
        """Return one complete trace, if it exists."""

        async with self._session_factory() as session:
            traces = list(
                (
                    await session.scalars(
                        select(Trace).order_by(Trace.timestamp.asc(), Trace.id.asc())
                    )
                ).all()
            )
            self._apply_anomaly_analysis(traces)
            return next((trace for trace in traces if trace.id == trace_id), None)

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
            traces = list(
                (
                    await session.scalars(select(Trace).order_by(Trace.duration_ms))
                ).all()
            )

        request_count = len(traces)
        if not request_count:
            return TraceMetrics(0, 0.0, 0.0, 0.0)

        durations = [trace.duration_ms for trace in traces]
        error_count = sum(
            (trace.status_code is not None and trace.status_code >= 500)
            or trace.error_type is not None
            for trace in traces
        )
        p95_index = max(0, (95 * request_count + 99) // 100 - 1)
        return TraceMetrics(
            request_count=request_count,
            error_rate=error_count / request_count,
            average_duration_ms=sum(durations) / request_count,
            p95_duration_ms=durations[p95_index],
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

    @classmethod
    def _apply_anomaly_analysis(cls, traces: list[Trace]) -> None:
        """Attach latency analysis based on earlier calls to the same endpoint."""

        prior_durations: dict[tuple[str, str], list[float]] = {}
        for trace in traces:
            endpoint = (trace.method, trace.path)
            baseline_samples = prior_durations.setdefault(endpoint, [])
            baseline_duration_ms = (
                sum(baseline_samples) / len(baseline_samples)
                if len(baseline_samples) >= cls._MIN_BASELINE_SAMPLES
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
            baseline_samples.append(trace.duration_ms)