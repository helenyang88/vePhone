from uuid import uuid4


def _create_business(client, name: str) -> str:
    response = client.post("/api/v1/business-spaces", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _create_case(client, title: str) -> str:
    response = client.post(
        "/api/v1/cases",
        json={
            "title": title,
            "module": "业务隔离",
            "content_markdown": "## 执行任务\n- 验证业务隔离",
            "tags": ["scope"],
            "automation_level": "auto",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_cases_and_tasks_are_scoped_by_current_business(authenticated_client):
    business_a = _create_business(authenticated_client, "业务A")
    business_b = _create_business(authenticated_client, "业务B")

    authenticated_client.headers["X-Business-Id"] = business_a
    case_id = _create_case(authenticated_client, "业务A用例")
    configured = authenticated_client.put("/api/v1/settings/runner", json={"mode": "mock"})
    assert configured.status_code == 200
    executed = authenticated_client.post(
        f"/api/v1/cases/{case_id}/execute",
        json={
            "idempotency_key": f"idem-{uuid4().hex}",
            "agent_config_mode": "global",
        },
    )
    assert executed.status_code == 201
    task_id = executed.json()["id"]

    authenticated_client.headers["X-Business-Id"] = business_b
    cases_b = authenticated_client.get("/api/v1/cases")
    assert cases_b.status_code == 200
    assert cases_b.json()["total"] == 0
    tasks_b = authenticated_client.get("/api/v1/tasks")
    assert tasks_b.status_code == 200
    assert tasks_b.json()["total"] == 0
    assert authenticated_client.get(f"/api/v1/cases/{case_id}").status_code == 404
    assert authenticated_client.get(f"/api/v1/tasks/{task_id}").status_code == 404

    authenticated_client.headers["X-Business-Id"] = business_a
    cases_a = authenticated_client.get("/api/v1/cases")
    assert cases_a.json()["total"] == 1
    tasks_a = authenticated_client.get("/api/v1/tasks")
    assert tasks_a.json()["total"] == 1
    runtime = authenticated_client.get(f"/api/v1/tasks/{task_id}/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["execution_config"]["business_id"] == business_a
    assert runtime.json()["execution_config"]["business_name_snapshot"] == "业务A"


def test_test_plans_are_scoped_by_current_business(authenticated_client):
    business_a = _create_business(authenticated_client, "计划业务A")
    business_b = _create_business(authenticated_client, "计划业务B")

    authenticated_client.headers["X-Business-Id"] = business_a
    first_case = _create_case(authenticated_client, "计划用例一")
    second_case = _create_case(authenticated_client, "计划用例二")
    created = authenticated_client.post(
        "/api/v1/test-plans",
        json={
            "name": "业务A计划",
            "description": "只属于业务A",
            "test_type": "regression",
            "tags": ["plan-scope"],
            "case_ids": [first_case, second_case],
        },
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]

    authenticated_client.headers["X-Business-Id"] = business_b
    listed_b = authenticated_client.get("/api/v1/test-plans")
    assert listed_b.status_code == 200
    assert listed_b.json()["total"] == 0
    assert authenticated_client.get(f"/api/v1/test-plans/{plan_id}").status_code == 404

    authenticated_client.headers["X-Business-Id"] = business_a
    listed_a = authenticated_client.get("/api/v1/test-plans")
    assert listed_a.status_code == 200
    assert listed_a.json()["total"] == 1


def test_plan_reports_are_scoped_by_current_business(authenticated_client):
    business_a = _create_business(authenticated_client, "报告业务A")
    business_b = _create_business(authenticated_client, "报告业务B")

    authenticated_client.headers["X-Business-Id"] = business_a
    configured = authenticated_client.put("/api/v1/settings/runner", json={"mode": "mock"})
    assert configured.status_code == 200
    first_case = _create_case(authenticated_client, "报告用例一")
    second_case = _create_case(authenticated_client, "报告用例二")
    plan = authenticated_client.post(
        "/api/v1/test-plans",
        json={
            "name": "报告计划",
            "description": None,
            "test_type": "regression",
            "tags": ["report-scope"],
            "case_ids": [first_case, second_case],
        },
    )
    assert plan.status_code == 201
    execution = authenticated_client.post(
        f"/api/v1/test-plans/{plan.json()['id']}/executions",
        json={
            "test_type": "regression",
            "device_strategy": "automatic",
            "pod_ids": [],
            "concurrency": 1,
            "agent_config_mode": "global",
            "idempotency_key": f"idem-{uuid4().hex}",
        },
    )
    assert execution.status_code == 201
    execution_id = execution.json()["id"]

    authenticated_client.headers["X-Business-Id"] = business_b
    reports_b = authenticated_client.get("/api/v1/task-reports")
    assert reports_b.status_code == 200
    assert reports_b.json()["total"] == 0
    assert authenticated_client.get(f"/api/v1/task-reports/{execution_id}").status_code == 404

    authenticated_client.headers["X-Business-Id"] = business_a
    reports_a = authenticated_client.get("/api/v1/task-reports")
    assert reports_a.status_code == 200
    assert reports_a.json()["total"] == 1
    detail = authenticated_client.get(f"/api/v1/task-reports/{execution_id}")
    assert detail.status_code == 200
    assert detail.json()["config_snapshot"]["business_id"] == business_a
