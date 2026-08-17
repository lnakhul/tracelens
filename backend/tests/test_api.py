from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from tracelens.config import Settings
from tracelens.main import create_app
from tracelens.services.traces import TraceData


def create_client(database_path: Path) -> TestClient:
    return TestClient(
        create_app(Settings(target_url="http://upstream.test", database_path=database_path))
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
            },
            {
                "id": 2,
                "timestamp": "2026-08-17T00:00:01Z",
                "method": "GET",
                "path": "/orders",
                "status_code": 500,
                "duration_ms": 50.0,
                "error_type": None,
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