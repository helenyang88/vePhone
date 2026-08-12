from datetime import timedelta

from fastapi import APIRouter, Request, status

from mua_platform.api.deps import CsrfSession, CurrentUser, Database
from mua_platform.api.errors import api_error
from mua_platform.cases.models import ScriptVersion, TestCase
from mua_platform.pods.repository import PodRepository
from mua_platform.pods.service import PodAllocationError, PodPoolService
from mua_platform.reusable_scripts.repository import ReusableScriptRepository
from mua_platform.reusable_scripts.schemas import (
    ExecuteReusableScript,
    ReusableScriptListResponse,
    ReusableScriptResponse,
    SaveReusableScript,
)
from mua_platform.reusable_scripts.service import (
    ReusableScriptError,
    ReusableScriptService,
)
from mua_platform.settings.repository import SettingRepository
from mua_platform.settings.schemas import RunnerExecutionSettingsError
from mua_platform.settings.service import SettingsService
from mua_platform.tasks.repository import SQLiteTaskRepository
from mua_platform.tasks.schemas import TaskResponse
from mua_platform.tasks.service import TaskService

router = APIRouter(prefix="/api/v1")


@router.post(
    "/tasks/{task_id}/reusable-script",
    response_model=ReusableScriptResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_reusable_script(
    task_id: str,
    payload: SaveReusableScript,
    db: Database,
    user: CurrentUser,
    _csrf_session: CsrfSession,
):
    try:
        return ReusableScriptService(ReusableScriptRepository(db)).save(
            task_id,
            payload,
            actor_id=str(user.id),
        )
    except ReusableScriptError as exc:
        raise _domain_error(exc) from exc


@router.get("/reusable-scripts", response_model=ReusableScriptListResponse)
def list_reusable_scripts(db: Database, _user: CurrentUser):
    items = ReusableScriptService(ReusableScriptRepository(db)).list()
    return {"items": items}


@router.get(
    "/reusable-scripts/{script_id}",
    response_model=ReusableScriptResponse,
)
def get_reusable_script(script_id: str, db: Database, _user: CurrentUser):
    try:
        return ReusableScriptService(ReusableScriptRepository(db)).get(script_id)
    except ReusableScriptError as exc:
        raise _domain_error(exc) from exc


@router.post(
    "/reusable-scripts/{script_id}/archive",
    response_model=ReusableScriptResponse,
)
def archive_reusable_script(
    script_id: str,
    db: Database,
    _user: CurrentUser,
    _csrf_session: CsrfSession,
):
    try:
        return ReusableScriptService(ReusableScriptRepository(db)).archive(script_id)
    except ReusableScriptError as exc:
        raise _domain_error(exc) from exc


@router.post(
    "/reusable-scripts/{script_id}/restore",
    response_model=ReusableScriptResponse,
)
def restore_reusable_script(
    script_id: str,
    db: Database,
    _user: CurrentUser,
    _csrf_session: CsrfSession,
):
    try:
        return ReusableScriptService(ReusableScriptRepository(db)).restore(script_id)
    except ReusableScriptError as exc:
        raise _domain_error(exc) from exc


@router.post(
    "/reusable-scripts/{script_id}/execute",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_reusable_script(
    script_id: str,
    payload: ExecuteReusableScript,
    request: Request,
    db: Database,
    _user: CurrentUser,
    _csrf_session: CsrfSession,
):
    async def allocate(
        script: ScriptVersion,
        idempotency_key: str,
        reusable_script_id: str,
    ):
        case = db.get(TestCase, script.case_id)
        if case is None:
            raise ReusableScriptError("script_source_not_found")
        runner_config = SettingsService(
            SettingRepository(
                db,
                request.app.state.setting_cipher,
                request.app.state.settings.runner_setting_defaults(),
            )
        ).get_runner_config()
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
        pod_pool = (
            PodPoolService(
                PodRepository(db),
                request.app.state.pod_gateway,
                request.app.state.pod_clock,
                config=runner_config,
            )
            if runner_config.mode == "mobile_use"
            else None
        )
        task_service = TaskService(
            SQLiteTaskRepository(db),
            None,
            execution_timeout=timedelta(
                seconds=request.app.state.settings.task_execution_timeout_seconds
            ),
            cancel_confirm_timeout=timedelta(
                seconds=request.app.state.settings.cancel_confirm_timeout_seconds
            ),
        )
        return await task_service.confirm_script(
            script,
            case.mock_scenario,
            idempotency_key,
            runner_config.mode,
            snapshot,
            pod_pool,
            execution_guard_script_id=reusable_script_id,
        )

    service = ReusableScriptService(
        ReusableScriptRepository(db),
        allocator=allocate,
    )
    try:
        task = await service.execute(
            script_id,
            payload.version_id,
            payload.idempotency_key,
        )
    except ReusableScriptError as exc:
        raise _domain_error(exc) from exc
    except PodAllocationError as exc:
        status_code = 502 if exc.code == "pod_pool_discovery_failed" else 409
        raise api_error(
            status_code,
            exc.code,
            "Pod allocation failed",
            {"request_id": exc.request_id} if exc.request_id else None,
        ) from exc
    except ValueError as exc:
        if str(exc).startswith("idempotency_conflict:"):
            raise api_error(
                409,
                "idempotency_conflict",
                "Idempotency key was already used for a different request",
            ) from exc
        if str(exc).startswith("execution_guard_failed:"):
            raise api_error(
                409,
                "script_archived",
                "Archived script cannot be executed",
            ) from exc
        raise
    await request.app.state.task_worker.enqueue(task.id)
    return task


def _domain_error(exc: ReusableScriptError):
    if exc.code in {
        "task_not_found",
        "script_source_not_found",
        "reusable_script_not_found",
        "script_version_not_found",
    }:
        return api_error(404, exc.code, "Reusable script resource not found")
    if exc.code == "script_archived":
        return api_error(409, exc.code, "Archived script cannot be executed")
    if exc.code == "script_not_saveable":
        return api_error(409, exc.code, "Task cannot be saved as a reusable script")
    return api_error(409, exc.code, "Reusable script state conflict")
