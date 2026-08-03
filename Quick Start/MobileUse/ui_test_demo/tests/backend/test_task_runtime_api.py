from types import SimpleNamespace

from mua_platform.tasks.models import Task, TaskRunnerConfig
from mua_platform.tasks.state_machine import ExecutionStatus


def _create_case(client, title: str) -> str:
    response = client.post(
        "/api/v1/cases",
        json={
            "title": title,
            "module": "执行轨迹",
            "content_markdown": "## 执行任务（必填）\n\n- 打开抖音APP",
            "tags": ["trace"],
            "automation_level": "auto",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class RecordingRuntimeGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def list_current_step(self, _config, _run_id):
        self.calls.append("ListAgentRunCurrentStep")
        return SimpleNamespace(
            payload={
                "Result": {
                    "RunId": "run-runtime",
                    "ThreadId": "thread-runtime",
                    "Status": 2,
                    "StepId": "step-current",
                    "Results": [],
                },
            },
        )

    async def get_result(self, _config, _run_id):
        self.calls.append("GetAgentResult")
        return SimpleNamespace(
            payload={
                "Result": {
                    "Content": "任务运行中",
                    "ScreenShots": {
                        "old-runtime-0": {
                            "screenshot": "https://example.invalid/old.png",
                        },
                        "run-runtime-0": {
                            "screenshot": "https://example.invalid/current.png",
                        },
                    },
                },
            },
        )

    async def list_task_by_thread(self, _config, *, thread_id, run_id):
        self.calls.append("ListAgentRunTaskByThread")
        return SimpleNamespace(
            payload={
                "Result": {
                    "Tasks": [
                        {
                            "RunId": run_id,
                            "ThreadId": thread_id,
                            "Status": 2,
                        },
                    ],
                },
            },
        )

    async def detail_task_by_thread(self, _config, *, thread_id: str, run_id: str):
        _ = (thread_id, run_id)
        self.calls.append("DetailAgentRunTaskByThread")
        return SimpleNamespace(payload={"Result": {"RunSteps": []}})


def test_runtime_skips_thread_detail_while_task_is_running(
    authenticated_client,
    monkeypatch,
):
    case_id = _create_case(authenticated_client, "运行中轨迹")
    with authenticated_client.app.state.session_factory() as db:
        task = Task(
            id="task_runtime_running",
            case_id=case_id,
            runner_type="mobile_use",
            scenario="运行中轨迹",
            execution_status=ExecutionStatus.RUNNING,
            idempotency_key="runtime-running",
            request_fingerprint="{}",
            remote_run_id="run-runtime",
            remote_thread_id="thread-runtime",
            created_by="admin",
        )
        task.runner_config = TaskRunnerConfig(
            config_snapshot={
                    "product_id": "prod-runtime",
                    "tos_bucket": "mua-test",
                    "tos_region": "cn-beijing",
            },
        )
        db.add(task)
        db.commit()

    gateway = RecordingRuntimeGateway()
    monkeypatch.setattr(
        "mua_platform.api.tasks.UniversalGateway",
        lambda: gateway,
    )

    response = authenticated_client.get("/api/v1/tasks/task_runtime_running/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["current_step"]["step_id"] == "step-current"
    assert body["thread_steps"] == []
    assert body["result"]["assets"]["screenshots"] == {
        "run-runtime-0": {"screenshot": "https://example.invalid/current.png"}
    }
    assert body["execution_config"]["source"] == "legacy"
    assert gateway.calls == [
        "ListAgentRunCurrentStep",
        "GetAgentResult",
        "ListAgentRunTaskByThread",
    ]
