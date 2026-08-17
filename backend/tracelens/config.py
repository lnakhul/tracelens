"""Runtime configuration and command-line parsing."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_CAPTURE_BODY_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated configuration shared by the application and proxy."""

    target_url: str
    port: int = DEFAULT_PORT
    bind_host: str = DEFAULT_BIND_HOST
    request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_capture_body_bytes: int = DEFAULT_MAX_CAPTURE_BODY_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_url", normalize_target_url(self.target_url))

        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.bind_host != DEFAULT_BIND_HOST:
            raise ValueError("V1 only permits binding to 127.0.0.1")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request timeout must be greater than zero")
        if self.max_capture_body_bytes < 0:
            raise ValueError("maximum capture body size cannot be negative")


def normalize_target_url(value: str) -> str:
    """Validate an upstream base URL and remove a trailing slash from its path."""

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("target must be an absolute http or https URL")
    if parsed.query or parsed.fragment:
        raise ValueError("target must not include a query string or fragment")

    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def parse_args(arguments: list[str] | None = None) -> Settings:
    """Parse command-line arguments into validated settings."""

    parser = argparse.ArgumentParser(
        prog="tracelens",
        description="Run a local HTTP observability proxy.",
    )
    parser.add_argument("--target", required=True, help="Absolute upstream http(s) URL")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local proxy port")

    args = parser.parse_args(arguments)
    try:
        return Settings(target_url=args.target, port=args.port)
    except ValueError as error:
        parser.error(str(error))
