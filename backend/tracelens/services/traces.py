"""Persistence service for captured HTTP traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tracelens.database.models import Trace


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


class TraceService:
    """Store captured exchanges independently of proxy request handling."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, trace_data: TraceData) -> None:
        """Persist a captured trace in its own short-lived database session."""

        async with self._session_factory() as session:
            session.add(Trace(**asdict(trace_data)))
            await session.commit()