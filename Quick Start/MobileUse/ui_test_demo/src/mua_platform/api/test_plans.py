from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, Response, status

from mua_platform.api.deps import CsrfSession, CurrentBusiness, CurrentUser, Database
from mua_platform.api.errors import api_error
from mua_platform.cases.service import CaseService
from mua_platform.settings.repository import SettingRepository
from mua_platform.settings.schemas import RunnerExecutionSettingsError
from mua_platform.settings.service import SettingsService
from mua_platform.tasks.state_machine import ExecutionStatus
from mua_platform.test_plans.executions import (
    PlanExecutionConcurrencyError,
    PlanExecutionCreate,
    PlanExecutionNotFoundError,
    PlanExecutionResponse,
    PlanExecutionService,
)
from mua_platform.test_plans.reports import PlanReportService
from mua_platform.test_plans.schemas import (
    CreatorListResponse,
    PlanReportDetail,
    PlanReportListResponse,
    PlanReportStats,
    ReportStatus,
    TagListResponse,
    TagResponse,
    TestPlanCaseListResponse,
    TestPlanListResponse,
    TestPlanResponse,
    TestPlanStatsResponse,
    TestPlanWrite,
)
from mua_platform.test_plans.service import (
    TagColorRegistryExhaustedError,
    TagColorService,
    TestPlanCaseNotFoundError,
    TestPlanCasesNotFoundError,
    TestPlanExecutionActiveError,
    TestPlanNameConflictError,
    TestPlanRequiresOneCaseError,
    TestPlanService,
)

router = APIRouter(prefix="/api/v1")


@router.get("/tags", response_model=TagListResponse)
def list_tags(
    db: Database,
    _user: CurrentUser,
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TagListResponse:
    items, total = TagColorService(db).list_paginated(
        search,
        page,
        page_size,
    )
    return TagListResponse(
        items=[
            TagResponse(
                name=item.tag_name,
                foreground_color=item.foreground_color,
                background_color=item.background_color,
                case_count=getattr(item, "case_count", 0),
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/test-plans/stats", response_model=TestPlanStatsResponse)
def get_test_plan_stats(
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
) -> TestPlanStatsResponse:
    return TestPlanStatsResponse(**TestPlanService(db).stats(business.id))


@router.get("/test-plans", response_model=TestPlanListResponse)
def list_test_plans(
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None),
    tag: str | None = Query(None),
    test_type: str | None = Query(None),
    created_by: str | None = Query(None),
) -> TestPlanListResponse:
    service = TestPlanService(db)
    plans, total = service.list_paginated(
        page,
        page_size,
        search,
        tag,
        test_type,
        business.id,
        created_by,
    )
    return TestPlanListResponse(
        items=service.responses(plans),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/test-plans/creators", response_model=CreatorListResponse)
def list_test_plan_creators(
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
) -> CreatorListResponse:
    return CreatorListResponse(items=TestPlanService(db).list_creators(business.id))


@router.get("/test-plans/tags", response_model=TagListResponse)
def list_test_plan_tags(
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
) -> TagListResponse:
    items = TestPlanService(db).list_plan_tags(business.id)
    return TagListResponse(
        items=items,
        total=len(items),
        page=1,
        page_size=max(len(items), 1),
    )


@router.post(
    "/test-plans",
    response_model=TestPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_test_plan(
    payload: TestPlanWrite,
    db: Database,
    user: CurrentUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> TestPlanResponse:
    service = TestPlanService(db)
    try:
        plan = service.create(
            payload,
            created_by=user.username,
            business_id=business.id,
        )
    except (
        TestPlanNameConflictError,
        TestPlanCasesNotFoundError,
        TagColorRegistryExhaustedError,
    ) as exc:
        raise _write_error(exc) from exc
    return service.response(plan)


@router.get(
    "/test-plans/{plan_id}",
    response_model=TestPlanResponse,
)
def get_test_plan(
    plan_id: str,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
) -> TestPlanResponse:
    service = TestPlanService(db)
    plan = service.get(plan_id, business.id)
    if plan is None:
        raise _not_found()
    return service.response(plan)


@router.put(
    "/test-plans/{plan_id}",
    response_model=TestPlanResponse,
)
def update_test_plan(
    plan_id: str,
    payload: TestPlanWrite,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> TestPlanResponse:
    service = TestPlanService(db)
    try:
        plan = service.update(plan_id, payload, business.id)
    except (
        TestPlanNameConflictError,
        TestPlanCasesNotFoundError,
        TagColorRegistryExhaustedError,
    ) as exc:
        raise _write_error(exc) from exc
    if plan is None:
        raise _not_found()
    return service.response(plan)


@router.delete(
    "/test-plans/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_test_plan(
    plan_id: str,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> Response:
    if not TestPlanService(db).delete(plan_id, datetime.now(UTC), business.id):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/test-plans/{plan_id}/cases",
    response_model=TestPlanCaseListResponse,
)
def list_test_plan_cases(
    plan_id: str,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> TestPlanCaseListResponse:
    service = TestPlanService(db)
    if not service.exists_active(plan_id, business.id):
        raise _not_found()
    cases, total = service.list_cases(plan_id, page, page_size, business.id)
    case_service = CaseService(db)
    return TestPlanCaseListResponse(
        items=case_service.case_responses(cases),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/test-plans/{plan_id}/cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_test_plan_case(
    plan_id: str,
    case_id: str,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> Response:
    service = TestPlanService(db)
    try:
        removed = service.remove_case(plan_id, case_id, business.id)
    except TestPlanCaseNotFoundError as exc:
        raise api_error(
            404,
            "case_not_in_test_plan",
            "Test case is not bound to this test plan",
        ) from exc
    except TestPlanRequiresOneCaseError as exc:
        raise api_error(
            409,
            "test_plan_requires_one_case",
            "Test plan must keep at least one test case",
        ) from exc
    except TestPlanExecutionActiveError as exc:
        raise api_error(
            409,
            "test_plan_execution_active",
            "Test plan has queued or running executions",
        ) from exc
    if not removed:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/test-plans/{plan_id}/executions",
    response_model=PlanReportListResponse,
)
def list_test_plan_executions(
    plan_id: str,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
) -> PlanReportListResponse:
    _require_report_page_size(page_size)
    if not TestPlanService(db).exists_active(plan_id, business.id):
        raise _not_found()
    items, total = PlanReportService(db).list_plan_executions(
        plan_id,
        page=page,
        page_size=page_size,
        business_id=business.id,
    )
    return PlanReportListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/task-reports/stats",
    response_model=PlanReportStats,
)
def get_task_report_stats(
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    test_plan_id: str | None = Query(None),
    status_filter: ReportStatus | None = Query(None, alias="status"),
    created_after: datetime | None = Query(None),
) -> PlanReportStats:
    return PlanReportService(db).stats(
        test_plan_id=test_plan_id,
        status=status_filter,
        created_after=created_after,
        business_id=business.id,
    )


@router.get(
    "/task-reports",
    response_model=PlanReportListResponse,
)
def list_task_reports(
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
    test_plan_id: str | None = Query(None),
    status_filter: ReportStatus | None = Query(None, alias="status"),
    created_after: datetime | None = Query(None),
    search: str | None = Query(None),
) -> PlanReportListResponse:
    _require_report_page_size(page_size)
    items, total = PlanReportService(db).list_paginated(
        page=page,
        page_size=page_size,
        test_plan_id=test_plan_id,
        status=status_filter,
        created_after=created_after,
        search=search,
        business_id=business.id,
    )
    return PlanReportListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/task-reports/{execution_id}",
    response_model=PlanReportDetail,
)
def get_task_report(
    execution_id: str,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
) -> PlanReportDetail:
    _require_report_page_size(page_size)
    detail = PlanReportService(db).get_detail(
        execution_id,
        page=page,
        page_size=page_size,
        business_id=business.id,
    )
    if detail is None:
        raise api_error(
            404,
            "task_report_not_found",
            "Task report not found",
        )
    return detail


@router.post(
    "/test-plans/{plan_id}/executions",
    response_model=PlanExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_plan_execution(
    plan_id: str,
    payload: PlanExecutionCreate,
    response: Response,
    request: Request,
    db: Database,
    user: CurrentUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> PlanExecutionResponse:
    runner_config = SettingsService(
        SettingRepository(
            db,
            request.app.state.setting_cipher,
            request.app.state.settings.runner_setting_defaults(),
        )
    ).get_runner_config(business.id)
    try:
        snapshot = runner_config.execution_snapshot()
    except RunnerExecutionSettingsError as exc:
        db.rollback()
        raise api_error(
            409,
            "runner_execution_settings_incomplete",
            "Runner execution settings are incomplete",
            {"missing_fields": exc.missing_fields},
        ) from exc
    snapshot["business_id"] = business.id
    snapshot["business_name_snapshot"] = business.name

    service = PlanExecutionService(db)
    try:
        result = service.create(
            plan_id,
            payload,
            created_by=user.username,
            runner_type=runner_config.mode,
            config_snapshot=snapshot,
            device_wait_timeout_seconds=(
                request.app.state.settings.device_wait_timeout_seconds
            ),
            business_id=business.id,
        )
    except PlanExecutionNotFoundError as exc:
        raise _not_found() from exc
    except PlanExecutionConcurrencyError as exc:
        raise api_error(
            422,
            "concurrency_exceeds_case_count",
            "Concurrency cannot exceed the plan case count",
        ) from exc
    except ValueError as exc:
        if str(exc).startswith("idempotency_conflict:"):
            raise api_error(
                409,
                "idempotency_conflict",
                "Idempotency key was already used for a different request",
            ) from exc
        raise

    if result.disposition == "existing":
        response.status_code = status.HTTP_200_OK
    if (
        result.disposition == "created"
        or result.batch.execution_status == ExecutionStatus.QUEUED
    ):
        schedule_batches = getattr(
            request.app.state,
            "schedule_batches",
            None,
        )
        if schedule_batches is not None:
            await schedule_batches()
    return service.response(result)


def _not_found():
    return api_error(
        404,
        "test_plan_not_found",
        "Test plan not found",
    )


def _require_report_page_size(page_size: int) -> None:
    if page_size not in {10, 20, 50}:
        raise api_error(
            422,
            "invalid_page_size",
            "Page size must be 10, 20, or 50",
        )


def _write_error(exc: Exception):
    if isinstance(exc, TestPlanNameConflictError):
        return api_error(
            409,
            "test_plan_name_conflict",
            "An active test plan already uses this name",
        )
    if isinstance(exc, TestPlanCasesNotFoundError):
        return api_error(
            404,
            "test_plan_cases_not_found",
            "One or more test cases were not found",
            {"case_ids": exc.case_ids},
        )
    return api_error(
        409,
        "tag_color_registry_exhausted",
        "No readable tag color is available",
    )
