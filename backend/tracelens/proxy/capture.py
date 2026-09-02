"""Safe, bounded capture of HTTP exchange data."""

from __future__ import annotations

import json
from collections.abc import Iterable

SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "x-api-key"})
TEXTUAL_CONTENT_TYPES = ("application/json", "application/x-www-form-urlencoded", "text/")


def sanitize_headers(headers: Iterable[tuple[str, str]]) -> str:
    """Serialize headers after redacting known credential-bearing fields."""

    sanitized = {
        name: "[REDACTED]" if name.lower() in SENSITIVE_HEADERS else value
        for name, value in headers
    }
    return json.dumps(sanitized, sort_keys=True)


def capture_body(headers: Iterable[tuple[str, str]], body: bytes, max_bytes: int) -> str | None:
    """Return a bounded textual body, or omit binary, unknown, and oversized data."""

    content_type = next(
        (value.lower() for name, value in headers if name.lower() == "content-type"),
        "",
    )
    content_encoding = next(
        (value.lower() for name, value in headers if name.lower() == "content-encoding"),
        "identity",
    )
    if (
        len(body) > max_bytes
        or not content_type.startswith(TEXTUAL_CONTENT_TYPES)
        or content_encoding not in {"", "identity"}
    ):
        return None

    return body.decode("utf-8", errors="replace")
