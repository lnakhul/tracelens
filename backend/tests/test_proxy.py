import httpx
import pytest
from fastapi.testclient import TestClient

from tracelens.config import Settings
from tracelens.main import create_app


def create_client(handler: httpx.MockTransport) -> TestClient:
    app = create_app(Settings(target_url="http://upstream.test/base"), transport=handler)
    return TestClient(app)


def test_proxy_forwards_method_path_query_body_and_end_to_end_headers() -> None:
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

    with create_client(httpx.MockTransport(upstream_handler)) as client:
        response = client.post(
            "/orders?source=dashboard",
            content=b'{"sku":"TL-1"}',
            headers={"x-request-id": "request-123", "connection": "close"},
        )

    assert response.status_code == 201
    assert response.json() == {"id": "order-42"}
    assert response.headers["x-upstream-request-id"] == "upstream-456"
    assert "connection" not in response.headers


def test_proxy_preserves_upstream_error_responses() -> None:
    def upstream_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"temporarily unavailable")

    with create_client(httpx.MockTransport(upstream_handler)) as client:
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
) -> None:
    def upstream_handler(request: httpx.Request) -> httpx.Response:
        raise error

    with create_client(httpx.MockTransport(upstream_handler)) as client:
        response = client.get("/unavailable")

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


def test_management_routes_are_not_forwarded() -> None:
    def upstream_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("management routes must not be forwarded")

    with create_client(httpx.MockTransport(upstream_handler)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}