"""Catch-all routes that forward traffic to the configured upstream service."""

import httpx
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response

from tracelens.proxy.forwarding import forward_request

router = APIRouter(include_in_schema=False)


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_request(request: Request, path: str) -> Response:
    """Forward non-management traffic, returning stable gateway errors on failure."""

    del path
    settings = request.app.state.settings
    client: httpx.AsyncClient = request.app.state.http_client

    try:
        return await forward_request(request, client, settings.target_url)
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"detail": "Upstream request timed out"})
    except httpx.TransportError:
        return JSONResponse(status_code=502, content={"detail": "Unable to reach upstream"})
    except httpx.HTTPError:
        return JSONResponse(status_code=502, content={"detail": "Proxy request failed"})
