"""Catch-all routes that forward traffic to the configured upstream service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter

import httpx
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response

from tracelens.proxy.capture import capture_body, sanitize_headers
from tracelens.proxy.forwarding import forward_request
from tracelens.services.traces import TraceData, TraceService

router = APIRouter(include_in_schema=False)
logger = logging.getLogger(__name__)


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_request(request: Request, path: str) -> Response:
    """Forward non-management traffic, returning stable gateway errors on failure."""

    del path
    settings = request.app.state.settings
    client: httpx.AsyncClient = request.app.state.http_client
    trace_service: TraceService = request.app.state.trace_service
    started_at = perf_counter()
    timestamp = datetime.now(UTC)
    response: Response
    request_body: bytes
    response_headers: list[tuple[str, str]]
    response_body: bytes
    status_code: int | None = None
    error_type: str | None = None

    try:
        response, request_body, upstream_response = await forward_request(
            request,
            client,
            settings.target_url,
        )
        status_code = upstream_response.status_code
        response_headers = list(upstream_response.headers.items())
        response_body = upstream_response.content
    except httpx.TimeoutException:
        request_body = await request.body()
        response = JSONResponse(status_code=504, content={"detail": "Upstream request timed out"})
        response_headers = list(response.headers.items())
        response_body = response.body
        error_type = "timeout"
    except httpx.TransportError:
        request_body = await request.body()
        response = JSONResponse(status_code=502, content={"detail": "Unable to reach upstream"})
        response_headers = list(response.headers.items())
        response_body = response.body
        error_type = "connect_error"
    except httpx.HTTPError:
        request_body = await request.body()
        response = JSONResponse(status_code=502, content={"detail": "Proxy request failed"})
        response_headers = list(response.headers.items())
        response_body = response.body
        error_type = "proxy_error"

    trace_data = TraceData(
        timestamp=timestamp,
        method=request.method.upper(),
        path=request.url.path,
        query_string=request.url.query or None,
        status_code=status_code,
        duration_ms=(perf_counter() - started_at) * 1000,
        error_type=error_type,
        request_headers=sanitize_headers(request.headers.items()),
        request_body=capture_body(
            request.headers.items(),
            request_body,
            settings.max_capture_body_bytes,
        ),
        response_headers=sanitize_headers(response_headers),
        response_body=capture_body(
            response_headers,
            response_body,
            settings.max_capture_body_bytes,
        ),
    )
    try:
        await trace_service.record(trace_data)
    except Exception:
        logger.exception("Unable to persist trace")

    return response
