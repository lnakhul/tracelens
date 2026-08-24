"""Management API routes available under /api."""

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from tracelens.api.schemas import (
    FailureAnalysisRequest,
    FailureAnalysisResponse,
    HealthResponse,
    MetricsResponse,
    TraceDetailResponse,
    TraceListResponse,
    TraceSummaryResponse,
)
from tracelens.services.failure_analysis import (
    FailureAnalysisProviderError,
    FailureAnalysisResponseError,
    FailureAnalysisService,
    FailureAnalysisUnavailableError,
)
from tracelens.services.traces import FailureAnalysisAuditData, TraceService

router = APIRouter(prefix="/api", tags=["management"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Confirm that the local TraceLens management API is available."""

    return HealthResponse(status="ok")


@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    path: str | None = None,
    status_code: int | None = None,
    min_duration_ms: Annotated[float | None, Query(ge=0)] = None,
    max_duration_ms: Annotated[float | None, Query(ge=0)] = None,
) -> TraceListResponse:
    """List captured traces using optional server-side filters."""

    trace_service: TraceService = request.app.state.trace_service
    page = await trace_service.list(
        limit=limit,
        offset=offset,
        path=path,
        status_code=status_code,
        min_duration_ms=min_duration_ms,
        max_duration_ms=max_duration_ms,
    )
    return TraceListResponse(
        items=[
            TraceSummaryResponse.model_validate(item, from_attributes=True) for item in page.items
        ],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(request: Request, trace_id: int) -> TraceDetailResponse:
    """Return the full locally captured record for one trace."""

    trace_service: TraceService = request.app.state.trace_service
    trace = await trace_service.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return TraceDetailResponse.model_validate(trace, from_attributes=True)


@router.delete("/traces/{trace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trace(request: Request, trace_id: int) -> Response:
    """Permanently delete one captured trace and its local analysis audit metadata."""

    trace_service: TraceService = request.app.state.trace_service
    if not await trace_service.delete(trace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/traces/{trace_id}/analysis", response_model=FailureAnalysisResponse)
async def analyze_trace_failure(
    request: Request,
    trace_id: int,
    analysis_request: FailureAnalysisRequest,
) -> FailureAnalysisResponse:
    """Request explicitly consented external analysis for one failed trace."""

    if not analysis_request.share_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Explicit consent is required before trace data can be shared",
        )
    trace_service: TraceService = request.app.state.trace_service
    trace = await trace_service.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    if (trace.status_code is None or trace.status_code < 500) and trace.error_type is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed traces can be analyzed",
        )

    analyzer: FailureAnalysisService = request.app.state.failure_analysis_service
    try:
        analysis = await analyzer.analyze(
            trace,
            await trace_service.successful_comparisons(trace),
            include_bodies=analysis_request.include_bodies,
        )
    except FailureAnalysisUnavailableError:
        await _record_analysis_audit(
            trace_service, trace_id, analysis_request.include_bodies, None, "unavailable", None, 0
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is not configured",
        ) from None
    except FailureAnalysisProviderError as error:
        await _record_analysis_audit(
            trace_service,
            trace_id,
            analysis_request.include_bodies,
            request.app.state.settings.ai_model,
            "provider_error",
            error.status_code,
            error.attempt_count,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from None
    except FailureAnalysisResponseError as error:
        await _record_analysis_audit(
            trace_service,
            trace_id,
            analysis_request.include_bodies,
            request.app.state.settings.ai_model,
            "invalid_response",
            None,
            error.attempt_count,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from None
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider returned an invalid analysis response",
        ) from None
    await _record_analysis_audit(
        trace_service,
        trace_id,
        analysis_request.include_bodies,
        analysis.model,
        "success",
        None,
        analysis.attempt_count,
    )
    return FailureAnalysisResponse(**asdict(analysis))


async def _record_analysis_audit(
    trace_service: TraceService,
    trace_id: int,
    include_bodies: bool,
    model: str | None,
    outcome: str,
    provider_status_code: int | None,
    attempt_count: int,
) -> None:
    """Persist non-sensitive analysis metadata without disrupting a provider response."""

    try:
        await trace_service.record_analysis_audit(
            FailureAnalysisAuditData(
                timestamp=datetime.now(UTC),
                trace_id=trace_id,
                model=model,
                include_bodies=include_bodies,
                outcome=outcome,
                provider_status_code=provider_status_code,
                attempt_count=attempt_count,
            )
        )
    except Exception:
        logger.exception("Unable to persist failure analysis audit")


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(request: Request) -> MetricsResponse:
    """Return metrics calculated from retained local traces."""

    trace_service: TraceService = request.app.state.trace_service
    metrics = await trace_service.metrics()
    return MetricsResponse(**asdict(metrics))


@router.delete("/traces", status_code=status.HTTP_204_NO_CONTENT)
async def clear_traces(request: Request) -> Response:
    """Permanently clear all local trace history."""

    trace_service: TraceService = request.app.state.trace_service
    await trace_service.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
