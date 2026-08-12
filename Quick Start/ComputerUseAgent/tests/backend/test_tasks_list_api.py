from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from mua_platform.tasks.models import Task
from mua_platform.tasks.repository import SQLiteTaskRepository
from mua_platform.tasks.state_machine import ExecutionStatus, Verdict


@pytest.fixture()
def authenticated_client(client, initialized_admin):
    return client


def _create_case(client, title: str) -> str:
    response = client.post(
        "/api/v1/cases",
        json={
            "title": title,
            "module": "登录",
            "content_markdown": "## 执行任务（必填）\n\n- 打开抖音APP",
            "tags": ["smoke"],
            "automation_level": "auto",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _seed_task(
    client,
    case_id: str,
    idempotency_key: str,
    *,
    created_by: str = "system",
    status: ExecutionStatus | None = None,
    verdict: Verdict | None = None,
) -> str:
    with client.app.state.session_factory() as db:
        repository = SQLiteTaskRepository(db)
        case = repository.get_case(case_id)
        assert case is not None
        result = repository.create_from_case(
            case,
            case.title,
            idempotency_key=idempotency_key,
            runner_type="mock",
            created_by=created_by,
        )
        task_id = result.task.id
        if status is not None:
            repository.mark_running(task_id)
            repository.finish(task_id, status, verdict, None)
        return task_id


def test_list_tasks_returns_paginated_envelope(authenticated_client):
    case_id = _create_case(authenticated_client, "分页任务用例")
    task_ids = [_seed_task(authenticated_client, case_id, f"exec-{i}") for i in range(3)]

    first = authenticated_client.get(
        "/api/v1/tasks", params={"page": 1, "page_size": 2}
    )
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == task_ids[-1]

    second = authenticated_client.get(
        "/api/v1/tasks", params={"page": 2, "page_size": 2}
    )
    assert len(second.json()["items"]) == 1


def test_get_task_exposes_remote_run_id(authenticated_client):
    case_id = _create_case(authenticated_client, "远端运行 ID 用例")
    task_id = _seed_task(authenticated_client, case_id, "exec-remote-run")
    with authenticated_client.app.state.session_factory() as db:
        task = db.get(Task, task_id)
        assert task is not None
        task.remote_run_id = "345569823413460992"
        db.commit()

    response = authenticated_client.get(f"/api/v1/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json()["remote_run_id"] == "345569823413460992"


def test_list_tasks_filters_by_status_and_verdict(authenticated_client):
    case_id = _create_case(authenticated_client, "筛选任务用例")
    passed = _seed_task(
        authenticated_client,
        case_id,
        "exec-pass",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.PASS,
    )
    failed = _seed_task(
        authenticated_client,
        case_id,
        "exec-fail",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.FAIL,
    )
    _seed_task(authenticated_client, case_id, "exec-queued")

    queued = authenticated_client.get("/api/v1/tasks", params={"status": "queued"})
    queued_ids = [item["id"] for item in queued.json()["items"]]
    assert passed not in queued_ids
    assert failed not in queued_ids
    assert queued.json()["total"] == 1

    only_pass = authenticated_client.get("/api/v1/tasks", params={"verdict": "pass"})
    pass_ids = [item["id"] for item in only_pass.json()["items"]]
    assert pass_ids == [passed]

    stopped = _seed_task(
        authenticated_client,
        case_id,
        "exec-stopped",
        status=ExecutionStatus.CANCELLED,
    )
    only_stopped = authenticated_client.get(
        "/api/v1/tasks",
        params={"verdict": "stopped"},
    )
    stopped_ids = [item["id"] for item in only_stopped.json()["items"]]
    assert stopped_ids == [stopped]


def test_review_completed_task_and_filter_by_manual_review(authenticated_client):
    case_id = _create_case(authenticated_client, "人工复核用例")
    passed = _seed_task(
        authenticated_client,
        case_id,
        "exec-review-pass",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.PASS,
    )
    failed = _seed_task(
        authenticated_client,
        case_id,
        "exec-review-fail",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.FAIL,
    )
    queued = _seed_task(authenticated_client, case_id, "exec-review-queued")

    reviewed = authenticated_client.put(
        f"/api/v1/tasks/{passed}/review",
        json={"review_result": "fail", "review_note": "实际未进入首页"},
    )

    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["review_result"] == "fail"
    assert body["review_note"] == "实际未进入首页"
    assert body["reviewed_by"] == "admin"
    assert body["reviewed_at"] is not None
    assert body["verdict"] == "pass"

    not_reviewable = authenticated_client.put(
        f"/api/v1/tasks/{queued}/review",
        json={"review_result": "pass"},
    )
    assert not_reviewable.status_code == 409
    assert not_reviewable.json()["error"]["code"] == "task_not_reviewable"

    only_manual_fail = authenticated_client.get(
        "/api/v1/tasks",
        params={"review_result": "fail"},
    )
    assert [item["id"] for item in only_manual_fail.json()["items"]] == [passed]

    unreviewed = authenticated_client.get(
        "/api/v1/tasks",
        params={"review_result": "unreviewed"},
    )
    assert [item["id"] for item in unreviewed.json()["items"]] == [failed]


def test_task_stats_reports_manual_review_fail_rate(authenticated_client):
    case_id = _create_case(authenticated_client, "人工复核统计用例")
    first = _seed_task(
        authenticated_client,
        case_id,
        "exec-review-stat-1",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.PASS,
    )
    second = _seed_task(
        authenticated_client,
        case_id,
        "exec-review-stat-2",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.FAIL,
    )
    _seed_task(
        authenticated_client,
        case_id,
        "exec-review-stat-3",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.PASS,
    )

    authenticated_client.put(
        f"/api/v1/tasks/{first}/review",
        json={"review_result": "fail"},
    )
    authenticated_client.put(
        f"/api/v1/tasks/{second}/review",
        json={"review_result": "pass"},
    )

    response = authenticated_client.get("/api/v1/tasks/stats")

    assert response.status_code == 200
    assert response.json()["manual_review_fail_count"] == 1
    assert response.json()["manual_review_total"] == 2
    assert response.json()["manual_review_fail_rate"] == 50


def test_list_tasks_treats_all_filters_as_unfiltered_and_searches_case_id(
    authenticated_client,
):
    first_case_id = _create_case(authenticated_client, "第一个用例")
    second_case_id = _create_case(authenticated_client, "第二个用例")
    first_task = _seed_task(authenticated_client, first_case_id, "exec-first")
    second_task = _seed_task(authenticated_client, second_case_id, "exec-second")

    unfiltered = authenticated_client.get(
        "/api/v1/tasks",
        params={"status": "all", "verdict": "all", "operator": "all"},
    )
    assert unfiltered.status_code == 200
    assert {item["id"] for item in unfiltered.json()["items"]} == {
        first_task,
        second_task,
    }

    by_case_id = authenticated_client.get(
        "/api/v1/tasks",
        params={"search": second_case_id},
    )
    assert by_case_id.status_code == 200
    assert [item["id"] for item in by_case_id.json()["items"]] == [second_task]


def test_list_tasks_filters_and_lists_operators(authenticated_client):
    case_id = _create_case(authenticated_client, "操作者筛选用例")
    alice_task = _seed_task(
        authenticated_client,
        case_id,
        "exec-alice",
        created_by="alice",
    )
    _seed_task(
        authenticated_client,
        case_id,
        "exec-bob",
        created_by="bob",
    )
    reviewed_task = _seed_task(
        authenticated_client,
        case_id,
        "exec-reviewed",
        created_by="system",
    )
    with authenticated_client.app.state.session_factory() as db:
        task = db.get(Task, reviewed_task)
        assert task is not None
        task.reviewed_by = "reviewer"
        db.commit()

    response = authenticated_client.get(
        "/api/v1/tasks",
        params={"operator": "alice"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [alice_task]
    assert response.json()["items"][0]["created_by"] == "alice"

    reviewed = authenticated_client.get(
        "/api/v1/tasks",
        params={"operator": "reviewer"},
    )
    assert reviewed.status_code == 200
    assert [item["id"] for item in reviewed.json()["items"]] == [reviewed_task]
    assert reviewed.json()["items"][0]["reviewed_by"] == "reviewer"

    operators = authenticated_client.get("/api/v1/tasks/operators")
    assert operators.status_code == 200
    assert operators.json() == {"items": ["alice", "bob", "reviewer", "system"]}


def test_list_tasks_filters_by_created_after(authenticated_client):
    case_id = _create_case(authenticated_client, "时间筛选用例")
    recent_task = _seed_task(authenticated_client, case_id, "exec-recent")
    old_task = _seed_task(authenticated_client, case_id, "exec-old")
    cutoff = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)

    with authenticated_client.app.state.session_factory() as db:
        recent = db.get(Task, recent_task)
        old = db.get(Task, old_task)
        assert recent is not None
        assert old is not None
        recent.created_at = cutoff + timedelta(hours=1)
        old.created_at = cutoff - timedelta(days=2)
        db.commit()

    response = authenticated_client.get(
        "/api/v1/tasks",
        params={"created_after": cutoff.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [recent_task]


def test_task_stats_reports_queued_and_running_counts(authenticated_client):
    case_id = _create_case(authenticated_client, "统计用例")
    _seed_task(authenticated_client, case_id, "exec-queued")
    _seed_task(
        authenticated_client,
        case_id,
        "exec-pass",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.PASS,
    )
    _seed_task(
        authenticated_client,
        case_id,
        "exec-fail",
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.FAIL,
    )
    _seed_task(
        authenticated_client,
        case_id,
        "exec-cancelled",
        status=ExecutionStatus.CANCELLED,
    )
    running_id = _seed_task(authenticated_client, case_id, "exec-running")
    invalid_queued_pass_id = _seed_task(
        authenticated_client,
        case_id,
        "exec-invalid-queued-pass",
    )
    illegal_verdict_id = _seed_task(
        authenticated_client,
        case_id,
        "exec-illegal-verdict",
    )
    with authenticated_client.app.state.session_factory() as db:
        repository = SQLiteTaskRepository(db)
        repository.mark_running(running_id)
        invalid_queued_pass = db.get(Task, invalid_queued_pass_id)
        assert invalid_queued_pass is not None
        invalid_queued_pass.verdict = Verdict.PASS
        db.execute(
            text(
                "UPDATE tasks "
                "SET execution_status = :status, verdict = :verdict "
                "WHERE id = :task_id"
            ),
            {
                "status": ExecutionStatus.RESULT_READY.value,
                "verdict": "illegal",
                "task_id": illegal_verdict_id,
            },
        )
        db.commit()

    response = authenticated_client.get("/api/v1/tasks/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": 7,
        "running": 1,
        "queued": 2,
        "pass_rate": 50,
        "manual_review_fail_count": 0,
        "manual_review_total": 0,
        "manual_review_fail_rate": 0,
    }


def test_cancelled_task_is_listed_with_cancelled_status(authenticated_client):
    case_id = _create_case(authenticated_client, "取消任务用例")
    task_id = _seed_task(authenticated_client, case_id, "exec-cancel")

    cancelled = authenticated_client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["execution_status"] == "cancelled"
    assert cancelled.json()["verdict"] is None

    listed = authenticated_client.get("/api/v1/tasks")
    task = next(item for item in listed.json()["items"] if item["id"] == task_id)
    assert task["execution_status"] == "cancelled"
    assert task["verdict"] is None


def test_list_tasks_search_matches_id(authenticated_client):
    case_id = _create_case(authenticated_client, "搜索任务用例")
    target = _seed_task(authenticated_client, case_id, "exec-search")

    response = authenticated_client.get("/api/v1/tasks", params={"search": target})
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [target]
