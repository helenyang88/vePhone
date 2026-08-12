import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mua_platform.config import Settings
from mua_platform.main import create_app


def assert_error_envelope(response, code: str) -> dict:
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"].startswith("req_")
    assert error["details"] == {}
    return error


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert_error_envelope(response, "not_found")


def test_method_not_allowed_uses_error_envelope(client):
    response = client.delete("/api/v1/setup/status")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert_error_envelope(response, "method_not_allowed")


def test_validation_error_omits_sensitive_input_and_documentation_url(client):
    sensitive_value = "sensitive-input-value"

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": [sensitive_value],
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 422
    errors = response.json()["error"]["details"]["errors"]
    assert errors
    assert all("input" not in error and "url" not in error for error in errors)
    assert sensitive_value not in response.text
    assert "errors.pydantic.dev" not in response.text


def test_request_body_over_one_megabyte_is_rejected_before_validation(client):
    response = client.post(
        "/api/v1/auth/login",
        content=b'{"oversized":"' + (b"x" * (1024 * 1024)) + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert_error_envelope(response, "request_too_large")
    assert "x" * 100 not in response.text


def test_unknown_exception_is_logged_without_sensitive_message(
    settings: Settings,
    caplog,
):
    app = create_app(settings)
    _add_crashing_route(app)

    with (
        caplog.at_level(logging.ERROR, logger="mua_platform.errors"),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.get("/_test/crash/path-sensitive-value")

    error = assert_error_envelope(response, "internal_server_error")
    assert response.status_code == 500
    record = next(record for record in caplog.records if record.name == "mua_platform.errors")
    assert record.request_id == error["request_id"]
    assert record.method == "GET"
    assert record.path == "/_test/crash/{secret}"
    assert record.exception_type == "RuntimeError"
    assert "SuperSecretPassword123!" not in caplog.text
    assert "token-sensitive-value" not in caplog.text
    assert "path-sensitive-value" not in caplog.text


def _add_crashing_route(app: FastAPI) -> None:
    @app.get("/_test/crash/{secret}")
    def crash(secret: str) -> None:
        raise RuntimeError(
            f"password=SuperSecretPassword123! token=token-sensitive-value path={secret}"
        )
