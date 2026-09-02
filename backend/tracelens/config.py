"""Runtime configuration and command-line parsing."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DEFAULT_BIND_HOST = "127.0.0.1"
DOCKER_BIND_HOST = "0.0.0.0"
CONTAINER_MODE_ENV = "TRACELENS_CONTAINER_MODE"
DEFAULT_PORT = 9000
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_CAPTURE_BODY_BYTES = 64 * 1024
DEFAULT_AI_MAX_CONTEXT_BYTES = 24 * 1024
DEFAULT_AI_MAX_RETRIES = 2


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated configuration shared by the application and proxy."""

    target_url: str
    port: int = DEFAULT_PORT
    bind_host: str = DEFAULT_BIND_HOST
    container_mode: bool = False
    request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_capture_body_bytes: int = DEFAULT_MAX_CAPTURE_BODY_BYTES
    database_path: Path = Path("tracelens.db")
    ai_endpoint: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    ai_max_context_bytes: int = DEFAULT_AI_MAX_CONTEXT_BYTES
    ai_max_retries: int = DEFAULT_AI_MAX_RETRIES
    retention_hours: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_url", normalize_target_url(self.target_url))

        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.bind_host == DOCKER_BIND_HOST and not self.container_mode:
            raise ValueError("non-loopback binding is reserved for container mode")
        if self.bind_host not in {DEFAULT_BIND_HOST, DOCKER_BIND_HOST}:
            raise ValueError("bind host must be 127.0.0.1 or the container interface")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request timeout must be greater than zero")
        if self.max_capture_body_bytes < 0:
            raise ValueError("maximum capture body size cannot be negative")
        if (self.ai_endpoint is None) != (self.ai_model is None):
            raise ValueError("AI endpoint and model must be configured together")
        if self.ai_max_context_bytes < 4 * 1024:
            raise ValueError("AI context limit must be at least 4096 bytes")
        if not 0 <= self.ai_max_retries <= 5:
            raise ValueError("AI retry count must be between 0 and 5")
        if self.retention_hours is not None and self.retention_hours < 1:
            raise ValueError("retention period must be at least one hour")


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
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("tracelens.db"),
        help="SQLite database file path",
    )
    parser.add_argument(
        "--ai-endpoint",
        help="OpenAI-compatible chat completions URL; analysis remains disabled when omitted",
    )
    parser.add_argument("--ai-model", help="Model name used with --ai-endpoint")
    parser.add_argument(
        "--ai-max-context-bytes",
        type=int,
        default=DEFAULT_AI_MAX_CONTEXT_BYTES,
        help="Maximum serialized trace context shared with the AI provider",
    )
    parser.add_argument(
        "--ai-max-retries",
        type=int,
        default=DEFAULT_AI_MAX_RETRIES,
        help="Retry count for AI rate limits and transient transport failures",
    )
    parser.add_argument(
        "--retention-hours",
        type=int,
        help="Automatically purge traces older than this period; disabled when omitted",
    )

    args = parser.parse_args(arguments)
    container_mode = os.getenv(CONTAINER_MODE_ENV) == "1"
    try:
        return Settings(
            target_url=args.target,
            port=args.port,
            bind_host=DOCKER_BIND_HOST if container_mode else DEFAULT_BIND_HOST,
            container_mode=container_mode,
            database_path=args.database_path,
            ai_endpoint=args.ai_endpoint,
            ai_model=args.ai_model,
            ai_api_key=os.getenv("TRACELENS_AI_API_KEY"),
            ai_max_context_bytes=args.ai_max_context_bytes,
            ai_max_retries=args.ai_max_retries,
            retention_hours=args.retention_hours,
        )
    except ValueError as error:
        parser.error(str(error))
