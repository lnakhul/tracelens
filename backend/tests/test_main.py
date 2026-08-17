from fastapi.testclient import TestClient

from tracelens.config import Settings
from tracelens.main import create_app


def test_application_factory_exposes_local_health_check(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_application_factory_retains_settings() -> None:
    settings = Settings(target_url="http://upstream.test", port=9001)

    app = create_app(settings)

    assert app.state.settings is settings