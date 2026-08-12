from fastapi import APIRouter, Request

from cua_platform.api.deps import AdminUser, CsrfSession, CurrentBusiness, Database
from cua_platform.api.errors import api_error
from cua_platform.pods.repository import PodRepository
from cua_platform.pods.service import PodDiscoveryError, PodPoolService
from cua_platform.settings.repository import SettingRepository
from cua_platform.settings.schemas import RunnerSettingsUpdate
from cua_platform.settings.service import SettingsService, RunnerSettingsValidationError

router = APIRouter(prefix="/api/v1/settings")
_POD_POOL_IDENTITY_FIELDS = {"access_key_id", "secret_access_key", "product_id"}


def _service(request: Request, db: Database) -> SettingsService:
    return SettingsService(
        SettingRepository(
            db,
            request.app.state.setting_cipher,
            request.app.state.settings.runner_setting_defaults(),
        )
    )


@router.get("")
def get_settings(
    request: Request,
    db: Database,
    _admin: AdminUser,
    business: CurrentBusiness,
) -> dict:
    return _service(request, db).get_public_settings(business.id)


@router.put("/runner")
async def update_runner(
    payload: RunnerSettingsUpdate,
    request: Request,
    db: Database,
    user: AdminUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> dict:
    async with request.app.state.runner_settings_lock:
        return await _update_runner_locked(payload, request, db, user.id, business.id)


async def _update_runner_locked(
    payload: RunnerSettingsUpdate,
    request: Request,
    db: Database,
    actor_user_id: int,
    business_id: str,
) -> dict:
    service = _service(request, db)
    previous_mode = service.get_runner_config(business_id).mode
    try:
        config = service.validate_runner(payload, business_id)
    except RunnerSettingsValidationError as exc:
        raise api_error(
            422,
            exc.code,
            "Runner settings are invalid",
            exc.details,
        ) from exc
    submitted_fields = (
        payload.mobile_use.model_fields_set if payload.mobile_use is not None else set()
    )
    identity_submitted = bool(submitted_fields & _POD_POOL_IDENTITY_FIELDS)
    switched_to_mobile_use = previous_mode != "mobile_use" and config.mode == "mobile_use"
    if config.mode == "mobile_use" and (identity_submitted or switched_to_mobile_use):
        db.rollback()
        pool = PodPoolService(
            PodRepository(db),
            request.app.state.pod_gateway,
            request.app.state.pod_clock,
        )
        try:
            await pool.refresh(
                config,
                before_sync=lambda: service.update_runner(
                    payload,
                    actor_user_id,
                    business_id,
                ),
            )
        except PodDiscoveryError as exc:
            db.rollback()
            raise api_error(
                502,
                exc.code,
                "Pod pool discovery failed",
                {"remote_request_id": exc.request_id} if exc.request_id else {},
            ) from exc
        result = service.get_public_settings(business_id)
    else:
        result = service.update_runner(payload, actor_user_id, business_id)
        db.commit()
    return result
