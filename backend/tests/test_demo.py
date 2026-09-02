from fastapi.testclient import TestClient

from tracelens.demo import create_demo_app, main


def test_demo_api_provides_success_failure_and_latency_scenarios() -> None:
    client = TestClient(create_demo_app())

    user = client.get("/users/42")
    order = client.post(
        "/orders",
        json={"customer_id": "cus_demo_001", "product_id": "prod_keyboard"},
    )
    failed_order = client.post("/orders", json={"product_id": "prod_keyboard"})
    report = client.get("/reports/daily?slow=true")

    assert user.status_code == 200
    assert user.json()["id"] == 42
    assert order.status_code == 201
    assert order.json()["status"] == "created"
    assert failed_order.status_code == 500
    assert "customer_id" in failed_order.json()["detail"]
    assert report.status_code == 200
    assert report.json()["slow"] is True


def test_demo_cli_accepts_container_bind_host(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: object, *, host: str, port: int) -> None:
        captured.update(app=app, host=host, port=port)

    monkeypatch.setattr("uvicorn.run", fake_run)

    main(["--bind-host", "0.0.0.0", "--port", "8100"])

    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8100
