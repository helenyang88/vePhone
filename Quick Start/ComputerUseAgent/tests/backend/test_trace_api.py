from datetime import UTC, datetime, timedelta

import pytest

from cua_platform.cases.models import TestCase as CaseModel
from cua_platform.tasks.models import Task, TaskEvent
from cua_platform.tasks.state_machine import ExecutionStatus, Verdict
from cua_platform.traces.repository import TraceRepository
from cua_platform.traces.schemas import TraceSpanDraft
from cua_platform.traces.service import TraceService

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


def add_task(client, task_id: str, *, historical: bool = False) -> None:
    with client.app.state.session_factory() as db:
        case = CaseModel(
            id=f"case-{task_id}",
            title="Trace API",
            module="Trace",
            content_markdown="## 执行任务\n\n- 验证 Trace API",
            tags=["trace"],
            automation_level="auto",
            created_by="admin",
        )
        task = Task(
            id=task_id,
            case_id=case.id,
            script_version_id=None,
            prompt_snapshot=case.content_markdown,
            runner_type="mobile_use",
            scenario="assertion_failure",
            created_by="admin",
            execution_status=ExecutionStatus.RESULT_READY,
            verdict=Verdict.FAIL,
            failure_type="assertion_failed",
            idempotency_key=f"idem-{task_id}",
            request_fingerprint="{}",
            created_at=NOW,
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
        )
        db.add(case)
        db.commit()
        db.add(task)
        db.commit()
        if historical:
            db.add_all(
                [
                    TaskEvent(
                        id=f"event-{task_id}-1",
                        task_id=task_id,
                        sequence=1,
                        event_type="task_started",
                        payload={"request_id": "must-not-be-inferred"},
                        created_at=NOW,
                    ),
                    TaskEvent(
                        id=f"event-{task_id}-2",
                        task_id=task_id,
                        sequence=2,
                        event_type="task_finished",
                        payload={"request_id": "must-not-be-inferred"},
                        created_at=NOW + timedelta(seconds=1),
                    ),
                ]
            )
            db.commit()


def draft(
    stable_key: str,
    *,
    parent_stable_key: str | None = None,
    kind: str = "call",
    status: str = "ok",
    request_id: str | None = None,
) -> TraceSpanDraft:
    return TraceSpanDraft(
        stable_key=stable_key,
        parent_stable_key=parent_stable_key,
        kind=kind,
        name="GetAgentResult",
        status=status,
        started_at=NOW,
        finished_at=NOW + timedelta(milliseconds=20),
        request_id=request_id,
        step_index=None,
        error_code=None,
        attributes={"action": "GetAgentResult", "method": "GET"},
    )


@pytest.fixture()
def task_with_trace(authenticated_client):
    add_task(authenticated_client, "task-with-trace")
    with authenticated_client.app.state.session_factory() as db:
        service = TraceService(TraceRepository(db))
        service.upsert(
            "task-with-trace",
            "mobile.result",
            draft("mobile.result", request_id="req-safe"),
        )
        service.upsert(
            "task-with-trace",
            "mobile.result.attempt.1",
            draft(
                "mobile.result.attempt.1",
                parent_stable_key="mobile.result",
                kind="attempt",
                request_id="req-attempt",
            ),
        )
    return "task-with-trace"


def test_trace_api_separates_call_execution_and_verdict(
    authenticated_client,
    task_with_trace,
):
    response = authenticated_client.get(f"/api/v1/tasks/{task_with_trace}/trace")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "spans"
    assert body["execution_status"] == "result_ready"
    assert body["verdict"] == "fail"
    assert body["spans"][0]["status"] == "ok"
    assert body["spans"][0]["request_id"] == "req-safe"
    assert body["spans"][0]["duration_ms"] == 20
    assert body["spans"][0]["children"][0]["request_id"] == "req-attempt"


def test_trace_api_supports_flat_view_and_attempt_filter(
    authenticated_client,
    task_with_trace,
):
    response = authenticated_client.get(
        f"/api/v1/tasks/{task_with_trace}/trace",
        params={"view": "flat", "include_attempts": "false"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["view"] == "flat"
    assert [span["kind"] for span in body["spans"]] == ["call"]
    assert "children" not in body["spans"][0]


@pytest.mark.parametrize(
    ("include_attempts", "expected_kinds"),
    [
        ("true", ["call", "attempt"]),
        ("false", ["call"]),
    ],
)
def test_trace_api_accepts_only_lowercase_boolean_literals(
    authenticated_client,
    task_with_trace,
    include_attempts,
    expected_kinds,
):
    response = authenticated_client.get(
        f"/api/v1/tasks/{task_with_trace}/trace",
        params={"view": "flat", "include_attempts": include_attempts},
    )

    assert response.status_code == 200
    assert [span["kind"] for span in response.json()["spans"]] == expected_kinds


def test_historical_trace_does_not_invent_remote_metadata(authenticated_client):
    add_task(authenticated_client, "historical-task", historical=True)

    response = authenticated_client.get("/api/v1/tasks/historical-task/trace")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "events"
    assert [span["name"] for span in body["spans"]] == [
        "task_started",
        "task_finished",
    ]
    assert all(span["request_id"] is None for span in body["spans"])
    assert all(span["duration_ms"] is None for span in body["spans"])
    assert all(span["attributes"] == {} for span in body["spans"])


@pytest.mark.parametrize(
    "params",
    [
        {"view": "graph"},
        {"include_attempts": "sometimes"},
        {"include_attempts": "1"},
        {"include_attempts": "0"},
        {"include_attempts": "yes"},
        {"include_attempts": "no"},
        {"include_attempts": "on"},
        {"include_attempts": "off"},
        {"include_attempts": "True"},
        {"include_attempts": "False"},
    ],
)
def test_trace_api_rejects_invalid_query_values(
    authenticated_client,
    task_with_trace,
    params,
):
    response = authenticated_client.get(
        f"/api/v1/tasks/{task_with_trace}/trace",
        params=params,
    )

    assert response.status_code == 422


def test_trace_api_returns_not_found(authenticated_client):
    response = authenticated_client.get("/api/v1/tasks/missing/trace")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "task_not_found"
