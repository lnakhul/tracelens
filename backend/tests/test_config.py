from pathlib import Path

import pytest

from tracelens.config import (
    CONTAINER_MODE_ENV,
    DEFAULT_BIND_HOST,
    DEFAULT_MAX_FORWARD_BODY_BYTES,
    DEFAULT_PORT,
    DOCKER_BIND_HOST,
    Settings,
    parse_args,
)


def test_settings_normalize_target_url() -> None:
    settings = Settings(target_url="https://api.example.test/v1/")

    assert settings.target_url == "https://api.example.test/v1"
    assert settings.port == DEFAULT_PORT
    assert settings.max_forward_body_bytes == DEFAULT_MAX_FORWARD_BODY_BYTES


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
            "--database-path",
            "/data/tracelens.db",
            "--retention-hours",
            "24",
        ]
    )

    assert settings == Settings(
        target_url="http://localhost:8000",
        port=9010,
        database_path=Path("/data/tracelens.db"),
        retention_hours=24,
    )


def test_settings_reject_non_loopback_bind_outside_container_mode() -> None:
    with pytest.raises(ValueError, match="container mode"):
        Settings(target_url="http://upstream.test", bind_host=DOCKER_BIND_HOST)


def test_parse_args_uses_container_interface_only_in_container_mode(monkeypatch) -> None:
    monkeypatch.setenv(CONTAINER_MODE_ENV, "1")

    settings = parse_args(["--target", "http://upstream.test"])

    assert settings.bind_host == DOCKER_BIND_HOST
    assert settings.container_mode is True


def test_parse_args_defaults_to_loopback_without_container_mode(monkeypatch) -> None:
    monkeypatch.delenv(CONTAINER_MODE_ENV, raising=False)

    settings = parse_args(["--target", "http://upstream.test"])

    assert settings.bind_host == DEFAULT_BIND_HOST
    assert settings.container_mode is False


def test_parse_args_rejects_public_bind_host_override() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--target",
                "http://upstream.test",
                "--bind-host",
                DOCKER_BIND_HOST,
            ]
        )


def test_settings_reject_non_positive_retention_period() -> None:
    with pytest.raises(ValueError, match="retention"):
        Settings(target_url="http://upstream.test", retention_hours=0)


def test_settings_reject_non_positive_forward_body_limit() -> None:
    with pytest.raises(ValueError, match="forwarded body"):
        Settings(target_url="http://upstream.test", max_forward_body_bytes=0)
