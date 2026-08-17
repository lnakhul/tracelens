import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tracelens.config import Settings
from tracelens.main import create_app


def create_client(handler: httpx.MockTransport, database_path: Path) -> TestClient:
    app = create_app(
        Settings(target_url="http://upstream.test/base", database_path=database_path),
        transport=handler,
    )
    return TestClient(app)


def read_traces(database_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute("SELECT * FROM traces ORDER BY id").fetchall()
    finally:
        connection.close()


def test_proxy_forwards_method_path_query_body_and_end_to_end_headers(tmp_path: Path) -> None:
    def upstream_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://upstream.test/base/orders?source=dashboard"
        assert request.content == b'{"sku":"TL-1"}'
        assert request.headers["x-request-id"] == "request-123"
        assert request.headers["host"] == "upstream.test"
        assert request.headers["connection"] != "close"
        return httpx.Response(
            201,
            headers={"x-upstream-request-id": "upstream-456", "connection": "close"},
            json={"id": "order-42"},
        )

    database_path = tmp_path / "traces.db"
    with create_client(httpx.MockTransport(upstream_handler), database_path) as client:
        response = client.post(
            "/orders?source=dashboard",
            content=b'{"sku":"TL-1"}',
            headers={
                "content-type": "application/json",
                "x-request-id": "request-123",
                "authorization": "Bearer secret-token",
                "connection": "close",
            },
        )

    assert response.status_code == 201
    assert response.json() == {"id": "order-42"}
    assert response.headers["x-upstream-request-id"] == "upstream-456"
    assert "connection" not in response.headers
    trace = read_traces(database_path)[0]
    assert trace["method"] == "POST"
    assert trace["path"] == "/orders"
    assert trace["query_string"] == "source=dashboard"
    assert trace["status_code"] == 201
    assert trace["error_type"] is None
    assert trace["duration_ms"] >= 0
    assert trace["request_body"] == '{"sku":"TL-1"}'
    assert json.loads(trace["request_headers"])["x-request-id"] == "request-123"
    assert json.loads(trace["request_headers"])["authorization"] == "[REDACTED]"
    assert json.loads(trace["response_headers"])["x-upstream-request-id"] == "upstream-456"
    assert trace["response_body"] == '{"id":"order-42"}'


def test_proxy_preserves_upstream_error_responses(tmp_path: Path) -> None:
    def upstream_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"temporarily unavailable")

    with create_client(httpx.MockTransport(upstream_handler), tmp_path / "traces.db") as client:
        response = client.get("/payments/91")

    assert response.status_code == 503
    assert response.content == b"temporarily unavailable"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (httpx.ConnectError("connection refused"), 502, "Unable to reach upstream"),
        (httpx.ReadTimeout("request timed out"), 504, "Upstream request timed out"),
    ],
)
def test_proxy_translates_transport_failures(
    error: httpx.TransportError,
    expected_status: int,
    expected_detail: str,
    tmp_path: Path,
) -> None:
    def upstream_handler(request: httpx.Request) -> httpx.Response:
        raise error

    database_path = tmp_path / "traces.db"
    with create_client(httpx.MockTransport(upstream_handler), database_path) as client:
        response = client.get("/unavailable")

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    trace = read_traces(database_path)[0]
    assert trace["status_code"] is None
    assert trace["error_type"] == ("timeout" if expected_status == 504 else "connect_error")


def test_management_routes_are_not_forwarded(tmp_path: Path) -> None:
    def upstream_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("management routes must not be forwarded")

    with create_client(httpx.MockTransport(upstream_handler), tmp_path / "traces.db") as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_persistence_failure_does_not_replace_upstream_response(tmp_path: Path) -> None:
    class FailingTraceService:
        async def record(self, trace_data: object) -> None:
            raise OSError("database unavailable")

    def upstream_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "order-42"})

    with create_client(httpx.MockTransport(upstream_handler), tmp_path / "traces.db") as client:
        client.app.state.trace_service = FailingTraceService()
        response = client.post("/orders", json={"sku": "TL-1"})

    assert response.status_code == 201
    assert response.json() == {"id": "order-42"}