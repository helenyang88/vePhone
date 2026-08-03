from dataclasses import asdict

from fastapi import APIRouter, Request

from mua_platform.api.deps import CsrfSession, CurrentUser, Database
from mua_platform.api.errors import api_error
from mua_platform.diagnostics.service import (
    DiagnosticsService,
    RunnerSettingsIncompleteError,
)
from mua_platform.settings.repository import SettingRepository
from mua_platform.settings.service import SettingsService

router = APIRouter(prefix="/api/v1/diagnostics")


def _service(request: Request, db: Database) -> DiagnosticsService:
    settings_service = SettingsService(
        SettingRepository(
            db,
            request.app.state.setting_cipher,
            request.app.state.settings.runner_setting_defaults(),
        )
    )
    return DiagnosticsService(
        settings_service,
        request.app.state.diagnostics_runner_factory,
        request.app.state.diagnostics_clock,
        timeout_seconds=request.app.state.diagnostics_timeout_seconds,
    )


@router.post("/runner")
async def validate_runner(
    request: Request,
    db: Database,
    _csrf_session: CsrfSession,
) -> dict:
    service = _service(request, db)
    try:
        result = await service.validate_runner()
    except RunnerSettingsIncompleteError as exc:
        raise api_error(
            409,
            exc.code,
            "Runner settings are incomplete",
            exc.details,
        ) from exc
    return {
        "checked_at": service.clock.now(),
        **asdict(result),
    }


@router.get("/pods")
async def list_pods(
    request: Request,
    db: Database,
    _user: CurrentUser,
) -> dict:
    service = _service(request, db)
    try:
        pods = await service.list_pods()
    except RunnerSettingsIncompleteError as exc:
        raise api_error(
            409,
            exc.code,
            "Runner settings are incomplete",
            exc.details,
        ) from exc
    return {
        "checked_at": service.clock.now(),
        "items": [asdict(pod) for pod in pods],
    }
