"""Opt-in external failure analysis for captured traces."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx

from tracelens.database.models import Trace


class FailureAnalysisUnavailableError(Exception):
    """Raised when external failure analysis has not been configured."""


class FailureAnalysisProviderError(Exception):
    """Raised when the configured provider rejects an analysis request."""

    def __init__(self, status_code: int | None, attempt_count: int) -> None:
        self.status_code = status_code
        self.attempt_count = attempt_count
        description = (
            f"HTTP {status_code}" if status_code is not None else "a transport error"
        )
        super().__init__(
            f"AI provider rejected the request ({description}). "
            "Check the API key, billing, and model access."
        )


class FailureAnalysisResponseError(Exception):
    """Raised when the provider does not return the required structured result."""

    def __init__(self, attempt_count: int) -> None:
        self.attempt_count = attempt_count
        super().__init__("The AI provider returned an invalid analysis response")


@dataclass(frozen=True, slots=True)
class FailureAnalysis:
    """Structured explanation returned by the configured language model."""

    likely_cause: str
    evidence: list[str]
    suggested_investigation: str
    model: str
    attempt_count: int
    data_shared: bool = True


class FailureAnalysisService:
    """Send a deliberately limited failure context to an OpenAI-compatible API."""

    def __init__(
        self,
        *,
        endpoint: str | None,
        api_key: str | None,
        model: str | None,
        http_client: httpx.AsyncClient,
        max_context_bytes: int,
        max_retries: int,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model
        self._http_client = http_client
        self._max_context_bytes = max_context_bytes
        self._max_retries = max_retries

    async def analyze(
        self,
        trace: Trace,
        successful_traces: list[Trace],
        *,
        include_bodies: bool,
    ) -> FailureAnalysis:
        """Analyze a failure using opted-in, redacted trace context."""

        if not self._endpoint or not self._api_key or not self._model:
            raise FailureAnalysisUnavailableError

        context = self._build_context(trace, successful_traces, include_bodies)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You analyze HTTP API failures. Respond only with a JSON object containing "
                        "likely_cause, evidence (an array of concise strings), and "
                        "suggested_investigation. State uncertainty rather than inventing facts."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(context),
                },
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "failure_analysis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "likely_cause": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                            "suggested_investigation": {"type": "string"},
                        },
                        "required": ["likely_cause", "evidence", "suggested_investigation"],
                        "additionalProperties": False,
                    },
                },
            },
        }
        response, attempt_count = await self._request_with_retries(payload)
        try:
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            if (
                not isinstance(result.get("likely_cause"), str)
                or not isinstance(result.get("evidence"), list)
                or not all(isinstance(item, str) for item in result["evidence"])
                or not isinstance(result.get("suggested_investigation"), str)
            ):
                raise TypeError
            return FailureAnalysis(
                likely_cause=str(result["likely_cause"]),
                evidence=[str(item) for item in result["evidence"]],
                suggested_investigation=str(result["suggested_investigation"]),
                model=self._model,
                attempt_count=attempt_count,
            )
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise FailureAnalysisResponseError(attempt_count) from error

    async def _request_with_retries(self, payload: dict[str, object]) -> tuple[httpx.Response, int]:
        for attempt_count in range(1, self._max_retries + 2):
            try:
                response = await self._http_client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            except httpx.TransportError as error:
                if attempt_count <= self._max_retries:
                    await asyncio.sleep(0.25 * attempt_count)
                    continue
                raise FailureAnalysisProviderError(None, attempt_count) from error
            if (
                response.status_code == httpx.codes.TOO_MANY_REQUESTS
                and attempt_count <= self._max_retries
            ):
                await asyncio.sleep(self._retry_delay(response, attempt_count))
                continue
            if response.is_error:
                raise FailureAnalysisProviderError(response.status_code, attempt_count)
            return response, attempt_count
        raise AssertionError("AI retry loop exited unexpectedly")

    def _build_context(
        self,
        trace: Trace,
        successful_traces: list[Trace],
        include_bodies: bool,
    ) -> dict[str, object]:
        traces = [trace, *successful_traces]
        field_limit = max(64, self._max_context_bytes // (len(traces) * 12))
        context: dict[str, object] = {
            "failed_trace": self._trace_context(trace, include_bodies, field_limit),
            "successful_comparisons": [
                self._trace_context(item, include_bodies, field_limit)
                for item in successful_traces
            ],
        }
        while (
            len(json.dumps(context).encode("utf-8")) > self._max_context_bytes
            and context["successful_comparisons"]
        ):
            context["successful_comparisons"].pop()
        return context

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt_count: int) -> float:
        retry_after = response.headers.get("retry-after")
        try:
            return min(float(retry_after), 2.0) if retry_after is not None else 0.25 * attempt_count
        except ValueError:
            return 0.25 * attempt_count

    @staticmethod
    def _trace_context(
        trace: Trace,
        include_bodies: bool,
        field_limit: int,
    ) -> dict[str, object]:
        context: dict[str, object] = {
            "method": trace.method,
            "path": trace.path,
            "status_code": trace.status_code,
            "duration_ms": trace.duration_ms,
            "error_type": trace.error_type,
            "request_headers": FailureAnalysisService._truncate(
                trace.request_headers, field_limit
            ),
            "response_headers": FailureAnalysisService._truncate(
                trace.response_headers, field_limit
            ),
        }
        if include_bodies:
            context["request_body"] = FailureAnalysisService._truncate(
                trace.request_body, field_limit
            )
            context["response_body"] = FailureAnalysisService._truncate(
                trace.response_body, field_limit
            )
        return context

    @staticmethod
    def _truncate(value: str | None, maximum_bytes: int) -> str | None:
        if value is None or len(value.encode("utf-8")) <= maximum_bytes:
            return value
        suffix = "...[TRUNCATED]"
        return value.encode("utf-8")[: maximum_bytes - len(suffix)].decode(
            "utf-8", errors="ignore"
        ) + suffix