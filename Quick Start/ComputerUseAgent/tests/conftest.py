import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The module-level ASGI app resolves settings during import.
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-at-least-32-bytes")
_test_data_dir = None
if "APP_DATA_DIR" not in os.environ:
    _test_data_dir = tempfile.TemporaryDirectory(prefix="mua-platform-tests-")
    os.environ["APP_DATA_DIR"] = _test_data_dir.name

from cua_platform.config import Settings  # noqa: E402
from cua_platform.main import app, create_app  # noqa: E402
from cua_platform.pods.schemas import ListPodPage  # noqa: E402


class EmptyPodGateway:
    async def list_all(self, _config) -> ListPodPage:
        return ListPodPage(items=(), next_token=None, request_id=None)


def pytest_sessionfinish():
    app.state.engine.dispose()
    if _test_data_dir is not None:
        _test_data_dir.cleanup()


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        app_secret_key="test-secret-key-at-least-32-bytes",
        app_data_dir=tmp_path,
        app_base_url="http://testserver",
        computer_use_access_key_id=None,
        computer_use_secret_access_key=None,
        computer_use_account_id=None,
        computer_use_tos_bucket=None,
        computer_use_tos_endpoint=None,
        computer_use_tos_region=None,
        computer_use_max_step=None,
        computer_use_timeout_seconds=None,
        computer_use_callback_info=None,
        computer_use_output_schema=None,
        computer_use_retry_limit=None,
        computer_use_system_prompt=None,
        computer_use_mcp_json=None,
        computer_use_max_output_tokens=None,
        computer_use_request_headers=None,
    )


@pytest.fixture()
def client(settings: Settings):
    with TestClient(create_app(settings, pod_gateway=EmptyPodGateway())) as test_client:
        yield test_client


@pytest.fixture()
def initialized_admin(client):
    response = client.post(
        "/api/v1/setup/admin",
        json={"username": "admin", "password": "StrongPassword123!"},
    )
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies["csrf"]
    return response.json()


@pytest.fixture()
def authenticated_client(client, initialized_admin):
    return client


@pytest.fixture()
def create_script(authenticated_client):
    def create(*, scenario: str = "success") -> str:
        case = authenticated_client.post(
            "/api/v1/cases",
            json={
                "title": f"手机号登录成功-{scenario}",
                "module": "登录",
                "content_markdown": (
                    "## 执行任务（必填）\n\n"
                    "- 打开 demo_app\n"
                    "- 验证首页已展示"
                ),
                "tags": ["smoke"],
                "automation_level": "auto",
            },
        )
        assert case.status_code == 201
        return case.json()["id"]

    return create
