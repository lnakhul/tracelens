"""Translation between incoming ASGI requests and upstream HTTPX requests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

import httpx
from fastapi import Request
from starlette.responses import Response

Header = tuple[bytes, bytes]

HOP_BY_HOP_HEADERS = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"te",
        b"trailer",
        b"transfer-encoding",
        b"upgrade",
        b"host",
    }
)


class RequestBodyTooLargeError(Exception):
    """Raised before an oversized client request is sent upstream."""


class UpstreamResponseTooLargeError(Exception):
    """Raised when an upstream response exceeds the configured buffer limit."""


def build_upstream_url(target_url: str, request: Request) -> str:
    """Combine the target with the original encoded request path and query."""

    raw_path = request.scope.get("raw_path")
    path = raw_path.decode("ascii") if isinstance(raw_path, bytes) else request.url.path
    raw_query = request.scope.get("query_string", b"")
    query = raw_query.decode("ascii") if isinstance(raw_query, bytes) else str(raw_query)
    url = f"{target_url}{path}"
    return f"{url}?{query}" if query else url


def filter_headers(
    headers: Iterable[Header],
    *,
    remove_content_length: bool = False,
) -> list[Header]:
    """Preserve end-to-end headers, including duplicates, and remove hop-by-hop fields."""

    header_list = list(headers)
    connection_tokens = {
        token.strip().lower()
        for name, value in header_list
        if name.lower() == b"connection"
        for token in value.split(b",")
        if token.strip()
    }
    excluded = HOP_BY_HOP_HEADERS | connection_tokens
    if remove_content_length:
        excluded = excluded | {b"content-length"}
    return [(name.lower(), value) for name, value in header_list if name.lower() not in excluded]


async def read_request_body(request: Request, maximum_bytes: int) -> bytes:
    """Read a request incrementally and reject it once the forwarding limit is exceeded."""

    _reject_oversized_content_length(
        request.headers.get("content-length"), maximum_bytes, RequestBodyTooLargeError
    )
    return await _read_bounded(request.stream(), maximum_bytes, RequestBodyTooLargeError)


async def forward_request(
    request: Request,
    request_body: bytes,
    client: httpx.AsyncClient,
    target_url: str,
    maximum_response_bytes: int,
) -> tuple[Response, int, list[tuple[str, str]], bytes]:
    """Forward one bounded request while preserving the raw upstream representation."""

    upstream_request = client.build_request(
        method=request.method,
        url=build_upstream_url(target_url, request),
        headers=filter_headers(request.headers.raw, remove_content_length=True),
        content=request_body,
    )
    upstream_response = await client.send(upstream_request, stream=True)
    try:
        _reject_oversized_content_length(
            upstream_response.headers.get("content-length"),
            maximum_response_bytes,
            UpstreamResponseTooLargeError,
        )
        response_body = await _read_response_body(
            upstream_response,
            maximum_response_bytes,
        )
        raw_headers = filter_headers(upstream_response.headers.raw)
        response = Response(content=response_body, status_code=upstream_response.status_code)
        response.raw_headers = raw_headers
        capture_headers = [
            (name.decode("latin-1"), value.decode("latin-1")) for name, value in raw_headers
        ]
        return response, upstream_response.status_code, capture_headers, response_body
    finally:
        await upstream_response.aclose()


async def _read_bounded(
    chunks: AsyncIterator[bytes],
    maximum_bytes: int,
    error_type: type[Exception],
) -> bytes:
    body = bytearray()
    async for chunk in chunks:
        if len(body) + len(chunk) > maximum_bytes:
            raise error_type
        body.extend(chunk)
    return bytes(body)


async def _read_response_body(
    response: httpx.Response,
    maximum_bytes: int,
) -> bytes:
    if response.is_stream_consumed:
        body = response.content
        if len(body) > maximum_bytes:
            raise UpstreamResponseTooLargeError
        return body

    return await _read_bounded(
        response.aiter_raw(),
        maximum_bytes,
        UpstreamResponseTooLargeError,
    )


def _reject_oversized_content_length(
    value: str | None,
    maximum_bytes: int,
    error_type: type[Exception],
) -> None:
    if value is None:
        return
    try:
        if int(value) > maximum_bytes:
            raise error_type
    except ValueError:
        # The HTTP server/client remains responsible for rejecting malformed framing.
        return
