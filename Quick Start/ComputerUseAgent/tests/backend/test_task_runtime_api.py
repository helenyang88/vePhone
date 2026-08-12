from types import SimpleNamespace

from cua_platform.tasks.models import Task, TaskRunnerConfig
from cua_platform.tasks.state_machine import ExecutionStatus


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
                    "TotalSteps": 4,
                    "DurationMs": 72000,
                    "DurationFmt": "1m12s",
                    "AvgStepDurationSec": 18,
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
                "request_headers": {
                    "X-Env": "runtime",
                    "X-Api-Key": "sk_live_1234567890abcdef",
                },
            },
        )
        db.add(task)
        db.commit()

    gateway = RecordingRuntimeGateway()
    monkeypatch.setattr(
        "cua_platform.api.tasks.UniversalGateway",
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
    assert body["result"]["assets"]["total_steps"] == 4
    assert body["result"]["assets"]["duration_ms"] == 72000
    assert body["result"]["assets"]["duration_fmt"] == "1m12s"
    assert body["result"]["assets"]["avg_step_duration_sec"] == 18
    assert body["execution_config"]["source"] == "legacy"
    assert body["execution_config"]["request_headers"] == {
        "configured": True,
        "names": ["X-Env", "X-Api-Key"],
        "items": [
            {"name": "X-Env", "value": "runtime"},
            {"name": "X-Api-Key", "value": "sk_l***cdef"},
        ],
    }
    assert "sk_live_1234567890abcdef" not in response.text
    assert gateway.calls == [
        "ListAgentRunCurrentStep",
        "GetAgentResult",
        "ListAgentRunTaskByThread",
    ]


def test_runtime_current_step_only_skips_result_and_thread_queries(
    authenticated_client,
    monkeypatch,
):
    case_id = _create_case(authenticated_client, "仅当前步骤轨迹")
    with authenticated_client.app.state.session_factory() as db:
        task = Task(
            id="task_runtime_current_only",
            case_id=case_id,
            runner_type="mobile_use",
            scenario="仅当前步骤轨迹",
            execution_status=ExecutionStatus.RUNNING,
            idempotency_key="runtime-current-only",
            request_fingerprint="{}",
            remote_run_id="run-runtime",
            remote_thread_id="thread-runtime",
            created_by="admin",
        )
        task.runner_config = TaskRunnerConfig(config_snapshot={})
        db.add(task)
        db.commit()

    gateway = RecordingRuntimeGateway()
    monkeypatch.setattr(
        "cua_platform.api.tasks.UniversalGateway",
        lambda: gateway,
    )

    response = authenticated_client.get(
        "/api/v1/tasks/task_runtime_current_only/runtime?current_step_only=true"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_step"]["step_id"] == "step-current"
    assert body["thread_groups"] == []
    assert body["thread_steps"] == []
    assert gateway.calls == ["ListAgentRunCurrentStep"]
