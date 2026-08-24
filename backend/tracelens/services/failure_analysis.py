"""Opt-in external failure analysis for captured traces."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from tracelens.database.models import Trace


class FailureAnalysisUnavailableError(Exception):
    """Raised when external failure analysis has not been configured."""


class FailureAnalysisProviderError(Exception):
    """Raised when the configured provider rejects an analysis request."""


@dataclass(frozen=True, slots=True)
class FailureAnalysis:
    """Structured explanation returned by the configured language model."""

    likely_cause: str
    evidence: list[str]
    suggested_investigation: str
    model: str
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
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model
        self._http_client = http_client

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
                    "content": json.dumps(
                        {
                            "failed_trace": self._trace_context(trace, include_bodies),
                            "successful_comparisons": [
                                self._trace_context(item, include_bodies)
                                for item in successful_traces
                            ],
                        }
                    ),
                },
            ],
            "temperature": 0,
        }
        response = await self._http_client.post(
            self._endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
        )
        if response.is_error:
            raise FailureAnalysisProviderError(
                f"AI provider rejected the request (HTTP {response.status_code}). "
                "Check the API key, billing, and model access."
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            return FailureAnalysis(
                likely_cause=str(result["likely_cause"]),
                evidence=[str(item) for item in result["evidence"]],
                suggested_investigation=str(result["suggested_investigation"]),
                model=self._model,
            )
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("The analysis provider returned an invalid response") from error

    @staticmethod
    def _trace_context(trace: Trace, include_bodies: bool) -> dict[str, object]:
        context: dict[str, object] = {
            "method": trace.method,
            "path": trace.path,
            "status_code": trace.status_code,
            "duration_ms": trace.duration_ms,
            "error_type": trace.error_type,
            "request_headers": trace.request_headers,
            "response_headers": trace.response_headers,
        }
        if include_bodies:
            context["request_body"] = trace.request_body
            context["response_body"] = trace.response_body
        return context