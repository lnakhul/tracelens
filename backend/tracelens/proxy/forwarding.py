"""Translation between incoming ASGI requests and upstream HTTPX requests."""

from __future__ import annotations

from collections.abc import Iterable

import httpx
from fastapi import Request
from starlette.responses import Response

HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
    }
)


def build_upstream_url(target_url: str, request: Request) -> str:
    """Combine the configured upstream base URL with an incoming path and query."""

    path = request.url.path
    query = request.url.query
    url = f"{target_url}{path}"
    return f"{url}?{query}" if query else url


def filter_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Return end-to-end headers suitable for forwarding in either direction."""

    return {
        name: value
        for name, value in headers
        if name.lower() not in HOP_BY_HOP_HEADERS
        and name.lower() != "content-length"
    }


async def forward_request(
    request: Request,
    client: httpx.AsyncClient,
    target_url: str,
) -> tuple[Response, bytes, httpx.Response]:
    """Forward one buffered request and return data needed to capture the exchange."""

    request_body = await request.body()
    upstream_request = client.build_request(
        method=request.method,
        url=build_upstream_url(target_url, request),
        headers=filter_headers(request.headers.items()),
        content=request_body,
    )
    upstream_response = await client.send(upstream_request)

    response = Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=filter_headers(upstream_response.headers.items()),
    )
    return response, request_body, upstream_response
