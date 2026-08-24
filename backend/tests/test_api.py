import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tracelens.config import Settings
from tracelens.main import create_app
from tracelens.services.traces import TraceData


def create_client(database_path: Path, *, retention_hours: int | None = None) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                target_url="http://upstream.test",
                database_path=database_path,
                retention_hours=retention_hours,
            )
        )
    )


def trace_data(
    *,
    timestamp: datetime,
    path: str,
    status_code: int | None,
    duration_ms: float,
    error_type: str | None = None,
) -> TraceData:
    return TraceData(
        timestamp=timestamp,
        method="GET",
        path=path,
        query_string=None,
        status_code=status_code,
        duration_ms=duration_ms,
        error_type=error_type,
        request_headers="{}",
        request_body=None,
        response_headers="{}",
        response_body=None,
    )


def test_trace_api_lists_filters_details_metrics_and_clears(tmp_path: Path) -> None:
    with create_client(tmp_path / "traces.db") as client:
        trace_service = client.app.state.trace_service
        timestamp = datetime(2026, 8, 17, tzinfo=UTC)
        for trace in (
            trace_data(timestamp=timestamp, path="/users", status_code=200, duration_ms=10),
            trace_data(
                timestamp=timestamp + timedelta(seconds=1),
                path="/orders",
                status_code=500,
                duration_ms=50,
            ),
            trace_data(
                timestamp=timestamp + timedelta(seconds=2),
                path="/orders",
                status_code=None,
                duration_ms=90,
                error_type="timeout",
            ),
        ):
            client.portal.call(trace_service.record, trace)

        listed = client.get("/api/traces?path=orders&min_duration_ms=40")
        metrics = client.get("/api/metrics")
        detail = client.get("/api/traces/2")
        missing = client.get("/api/traces/999")
        cleared = client.delete("/api/traces")
        empty = client.get("/api/traces")

    assert listed.status_code == 200
    assert listed.json() == {
        "items": [
            {
                "id": 3,
                "timestamp": "2026-08-17T00:00:02Z",
                "method": "GET",
                "path": "/orders",
                "status_code": None,
                "duration_ms": 90.0,
                "error_type": "timeout",
                "baseline_duration_ms": None,
                "latency_increase_ratio": None,
                "is_anomaly": False,
            },
            {
                "id": 2,
                "timestamp": "2026-08-17T00:00:01Z",
                "method": "GET",
                "path": "/orders",
                "status_code": 500,
                "duration_ms": 50.0,
                "error_type": None,
                "baseline_duration_ms": None,
                "latency_increase_ratio": None,
                "is_anomaly": False,
            },
        ],
        "total": 2,
        "limit": 50,
        "offset": 0,
    }
    assert metrics.status_code == 200
    assert metrics.json() == {
        "request_count": 3,
        "error_rate": 2 / 3,
        "average_duration_ms": 50.0,
        "p95_duration_ms": 90.0,
    }
    assert detail.status_code == 200
    assert detail.json()["path"] == "/orders"
    assert detail.json()["status_code"] == 500
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Trace not found"}
    assert cleared.status_code == 204
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0


def test_trace_api_rejects_invalid_pagination_and_latency_filters(tmp_path: Path) -> None:
    with create_client(tmp_path / "traces.db") as client:
        invalid_limit = client.get("/api/traces?limit=0")
        invalid_duration = client.get("/api/traces?min_duration_ms=-1")

    assert invalid_limit.status_code == 422
    assert invalid_duration.status_code == 422


def test_trace_api_deletes_one_trace_and_expired_traces(tmp_path: Path) -> None:
    with create_client(tmp_path / "traces.db", retention_hours=1) as client:
        trace_service = client.app.state.trace_service
        timestamp = datetime.now(UTC)
        client.portal.call(
            trace_service.record,
            trace_data(
                timestamp=timestamp - timedelta(hours=2),
                path="/expired",
                status_code=200,
                duration_ms=10,
            ),
        )
        client.portal.call(
            trace_service.record,
            trace_data(timestamp=timestamp, path="/orders", status_code=500, duration_ms=50),
        )

        listed = client.get("/api/traces")
    retained_trace_id = listed.json()["items"][0]["id"]
    deleted = client.delete(f"/api/traces/{retained_trace_id}")
    missing = client.delete(f"/api/traces/{retained_trace_id}")

    assert [item["path"] for item in listed.json()["items"]] == ["/orders"]
    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_trace_api_flags_request_slower_than_endpoint_baseline(tmp_path: Path) -> None:
    with create_client(tmp_path / "traces.db") as client:
        trace_service = client.app.state.trace_service
        timestamp = datetime(2026, 8, 17, tzinfo=UTC)
        for index, duration_ms in enumerate((100, 110, 90, 100, 100, 250)):
            client.portal.call(
                trace_service.record,
                trace_data(
                    timestamp=timestamp + timedelta(seconds=index),
                    path="/orders",
                    status_code=200,
                    duration_ms=duration_ms,
                ),
            )

        listed = client.get("/api/traces")
        detail = client.get("/api/traces/6")

    assert listed.status_code == 200
    slow_trace = listed.json()["items"][0]
    assert slow_trace["baseline_duration_ms"] == 100.0
    assert slow_trace["latency_increase_ratio"] == 2.5
    assert slow_trace["is_anomaly"] is True
    assert listed.json()["items"][1]["is_anomaly"] is False
    assert detail.status_code == 200
    assert detail.json()["is_anomaly"] is True


def test_failure_analysis_requires_consent_and_uses_opted_in_context(tmp_path: Path) -> None:
    attempts = 0

    def ai_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        payload = json.loads(request.content)
        shared_trace = payload["messages"][1]["content"]
        assert "request_body" not in shared_trace
        assert request.headers["authorization"] == "Bearer test-key"
        assert payload["response_format"]["json_schema"]["strict"] is True
        if attempts == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"likely_cause":"Upstream failed",'
                                '"evidence":["The trace returned 500"],'
                                '"suggested_investigation":"Check upstream logs"}'
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(
        target_url="http://upstream.test",
        database_path=tmp_path / "traces.db",
        ai_endpoint="https://ai.example.test/v1/chat/completions",
        ai_model="test-model",
        ai_api_key="test-key",
    )
    with TestClient(create_app(settings, ai_transport=httpx.MockTransport(ai_handler))) as client:
        trace_service = client.app.state.trace_service
        client.portal.call(
            trace_service.record,
            replace(
                trace_data(
                    timestamp=datetime(2026, 8, 17, tzinfo=UTC),
                    path="/orders",
                    status_code=500,
                    duration_ms=50,
                ),
                request_headers="x" * 10_000,
                response_headers="y" * 10_000,
            ),
        )
        without_consent = client.post("/api/traces/1/analysis", json={"share_data": False})
        analysis = client.post("/api/traces/1/analysis", json={"share_data": True})
        audits = client.portal.call(trace_service.analysis_audits, 1)

    assert without_consent.status_code == 403
    assert analysis.status_code == 200
    assert analysis.json() == {
        "likely_cause": "Upstream failed",
        "evidence": ["The trace returned 500"],
        "suggested_investigation": "Check upstream logs",
        "model": "test-model",
        "data_shared": True,
    }
    assert attempts == 2
    assert len(audits) == 1
    assert audits[0].outcome == "success"
    assert audits[0].attempt_count == 2
    assert audits[0].include_bodies is False


def test_failure_analysis_reports_sanitized_provider_rejection(tmp_path: Path) -> None:
    settings = Settings(
        target_url="http://upstream.test",
        database_path=tmp_path / "traces.db",
        ai_endpoint="https://ai.example.test/v1/chat/completions",
        ai_model="test-model",
        ai_api_key="test-key",
    )
    with TestClient(
        create_app(
            settings,
            ai_transport=httpx.MockTransport(lambda _: httpx.Response(401)),
        )
    ) as client:
        trace_service = client.app.state.trace_service
        client.portal.call(
            trace_service.record,
            trace_data(
                timestamp=datetime(2026, 8, 17, tzinfo=UTC),
                path="/orders",
                status_code=500,
                duration_ms=50,
            ),
        )
        response = client.post("/api/traces/1/analysis", json={"share_data": True})
        audits = client.portal.call(trace_service.analysis_audits, 1)

    assert response.status_code == 502
    assert response.json() == {
        "detail": "AI provider rejected the request (HTTP 401). "
        "Check the API key, billing, and model access."
    }
    assert len(audits) == 1
    assert audits[0].outcome == "provider_error"
    assert audits[0].provider_status_code == 401


def test_failure_analysis_caps_shared_context(tmp_path: Path) -> None:
    def ai_handler(request: httpx.Request) -> httpx.Response:
        context = json.loads(request.content)["messages"][1]["content"]
        assert len(context.encode("utf-8")) <= 4096
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"likely_cause":"Unknown","evidence":[],'
                                '"suggested_investigation":"Inspect the trace"}'
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(
        target_url="http://upstream.test",
        database_path=tmp_path / "traces.db",
        ai_endpoint="https://ai.example.test/v1/chat/completions",
        ai_model="test-model",
        ai_api_key="test-key",
        ai_max_context_bytes=4096,
    )
    with TestClient(create_app(settings, ai_transport=httpx.MockTransport(ai_handler))) as client:
        trace_service = client.app.state.trace_service
        client.portal.call(
            trace_service.record,
            trace_data(
                timestamp=datetime(2026, 8, 17, tzinfo=UTC),
                path="/orders",
                status_code=500,
                duration_ms=50,
            ),
        )
        response = client.post("/api/traces/1/analysis", json={"share_data": True})

    assert response.status_code == 200