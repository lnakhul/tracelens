from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tracelens.config import Settings
from tracelens.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(target_url="http://upstream.test")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
