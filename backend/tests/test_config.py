from pathlib import Path

import pytest

from tracelens.config import DEFAULT_PORT, DOCKER_BIND_HOST, Settings, parse_args


def test_settings_normalize_target_url() -> None:
    settings = Settings(target_url="https://api.example.test/v1/")

    assert settings.target_url == "https://api.example.test/v1"
    assert settings.port == DEFAULT_PORT


@pytest.mark.parametrize(
    "target_url",
    ["api.example.test", "ftp://api.example.test", "http://api.example.test?debug=true"],
)
def test_settings_reject_invalid_target_url(target_url: str) -> None:
    with pytest.raises(ValueError, match="target"):
        Settings(target_url=target_url)


def test_parse_args_reads_target_and_port() -> None:
    settings = parse_args(
        [
            "--target",
            "http://localhost:8000",
            "--port",
            "9010",
            "--bind-host",
            DOCKER_BIND_HOST,
            "--database-path",
            "/data/tracelens.db",
            "--retention-hours",
            "24",
        ]
    )

    assert settings == Settings(
        target_url="http://localhost:8000",
        port=9010,
        bind_host=DOCKER_BIND_HOST,
        database_path=Path("/data/tracelens.db"),
        retention_hours=24,
    )


def test_settings_reject_non_positive_retention_period() -> None:
    with pytest.raises(ValueError, match="retention"):
        Settings(target_url="http://upstream.test", retention_hours=0)
