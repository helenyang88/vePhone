from dataclasses import fields, is_dataclass
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from mua_platform.api.deps import CsrfSession, CurrentBusiness, CurrentUser, Database
from mua_platform.api.errors import api_error
from mua_platform.pods.repository import PodRepository
from mua_platform.pods.service import PodDiscoveryError, PodPoolService
from mua_platform.runners.universal_gateway import UniversalRemoteError
from mua_platform.settings.repository import SettingRepository
from mua_platform.settings.service import SettingsService

router = APIRouter(prefix="/api/v1/pod-pool")


def _service(request: Request, db: Database) -> tuple[PodPoolService, SettingsService]:
    pool = PodPoolService(
        PodRepository(db),
        request.app.state.pod_gateway,
        request.app.state.pod_clock,
    )
    settings = SettingsService(
        SettingRepository(
            db,
            request.app.state.setting_cipher,
            request.app.state.settings.runner_setting_defaults(),
        )
    )
    return pool, settings


def _serialize(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_serialize(v) for v in value]
    if is_dataclass(value):
        return {f.name: _serialize(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def _missing_stream_settings(config) -> list[str]:
    missing = []
    if not config.access_key_id:
        missing.append("access_key_id")
    if not config.secret_access_key:
        missing.append("secret_access_key")
    if not config.product_id:
        missing.append("product_id")
    if not config.account_id:
        missing.append("account_id")
    if not config.sts_role_trn:
        missing.append("sts_role_trn")
    return missing


async def _ensure_pod_exists(pool: PodPoolService, repo: PodRepository, config, pod_id: str) -> None:
    if config.product_id is None:
        raise api_error(
            409,
            "runner_settings_incomplete",
            "Runner settings are incomplete",
        )
    if repo.get(config.product_id, pod_id) is not None:
        return
    try:
        await pool.refresh(config)
    except PodDiscoveryError as exc:
        raise api_error(
            502,
            exc.code,
            "Pod pool discovery failed",
            {"remote_request_id": exc.request_id} if exc.request_id else {},
        ) from exc
    if repo.get(config.product_id, pod_id) is None:
        raise HTTPException(status_code=404, detail="pod_not_found")


@router.get("")
def list_pod_pool(
    request: Request,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
) -> dict:
    pool, settings = _service(request, db)
    try:
        snapshot = pool.list_cached(settings.get_runner_config(business.id))
    except ValueError as exc:
        raise api_error(
            409,
            "runner_settings_incomplete",
            "Runner settings are incomplete",
        ) from exc
    return _serialize(snapshot)


@router.get("/{pod_id}")
async def get_pod_detail(
    pod_id: str,
    request: Request,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
) -> dict:
    pool, settings = _service(request, db)
    repo = PodRepository(db)
    try:
        config = settings.get_runner_config(business.id)
    except ValueError as exc:
        raise api_error(
            409,
            "runner_settings_incomplete",
            "Runner settings are incomplete",
        ) from exc
    existing = repo.get(config.product_id, pod_id)
    if existing is None:
        try:
            await pool.refresh(config)
        except PodDiscoveryError as exc:
            raise api_error(
                502,
                exc.code,
                "Pod pool discovery failed",
                {"remote_request_id": exc.request_id} if exc.request_id else {},
            ) from exc
        existing = repo.get(config.product_id, pod_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="pod_not_found")
    try:
        detail = await repo.fetch_detail(
            request.app.state.pod_gateway,
            config,
            config.product_id,
            pod_id,
        )
    except UniversalRemoteError as exc:
        cached = repo.get_detail(config.product_id, pod_id)
        if cached[1] is not None:
            return _serialize(cached[1])
        raise api_error(
            502,
            exc.code or "pod_detail_failed",
            "Pod detail request failed",
            {"remote_request_id": exc.request_id} if exc.request_id else {},
        ) from exc
    return _serialize(detail)


@router.post("/refresh")
async def refresh_pod_pool(
    request: Request,
    db: Database,
    _user: CurrentUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> dict:
    pool, settings = _service(request, db)
    try:
        snapshot = await pool.refresh(settings.get_runner_config(business.id))
    except ValueError as exc:
        raise api_error(
            409,
            "runner_settings_incomplete",
            "Runner settings are incomplete",
        ) from exc
    except PodDiscoveryError as exc:
        raise api_error(
            502,
            exc.code,
            "Pod pool discovery failed",
            {"remote_request_id": exc.request_id} if exc.request_id else {},
        ) from exc
    return _serialize(snapshot)


@router.post("/{pod_id}/stream-session")
async def create_pod_stream_session(
    pod_id: str,
    request: Request,
    db: Database,
    user: CurrentUser,
    business: CurrentBusiness,
    _csrf_session: CsrfSession,
) -> dict:
    pool, settings = _service(request, db)
    repo = PodRepository(db)
    try:
        config = settings.get_runner_config(business.id)
    except ValueError as exc:
        raise api_error(
            409,
            "runner_settings_incomplete",
            "Runner settings are incomplete",
        ) from exc

    missing_fields = _missing_stream_settings(config)
    if missing_fields:
        raise api_error(
            409,
            "stream_settings_incomplete",
            "Stream settings are incomplete",
            {"missing_fields": missing_fields},
        )

    await _ensure_pod_exists(pool, repo, config, pod_id)
    user_id = f"mua-{user.username}"
    try:
        token = await request.app.state.stream_token_gateway.assume_role(
            config,
            pod_id=pod_id,
            user_id=user_id,
        )
    except UniversalRemoteError as exc:
        raise api_error(
            502,
            exc.code or "stream_token_failed",
            "Stream token request failed",
            {"remote_request_id": exc.request_id} if exc.request_id else {},
        ) from exc

    return {
        "account_id": config.account_id,
        "product_id": config.product_id,
        "pod_id": pod_id,
        "user_id": user_id,
        "token": token,
    }
