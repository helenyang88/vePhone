from fastapi import APIRouter, Query, Request, status

from cua_platform.api.deps import CsrfSession, CurrentBusiness, CurrentUser, Database
from cua_platform.api.errors import api_error
from cua_platform.business.schemas import (
    BusinessSpaceCreate,
    BusinessSpaceListResponse,
    BusinessSpaceResponse,
    BusinessSpaceUpdate,
)
from cua_platform.business.service import BusinessSpaceService
from cua_platform.settings.repository import SettingRepository
from cua_platform.settings.service import SettingsService

router = APIRouter(prefix="/api/v1/business-spaces")


@router.get("", response_model=BusinessSpaceListResponse)
def list_business_spaces(
    _user: CurrentUser,
    db: Database,
) -> BusinessSpaceListResponse:
    return BusinessSpaceListResponse(
        items=[
            BusinessSpaceResponse.model_validate(business)
            for business in BusinessSpaceService(db).list_active()
        ]
    )


@router.post(
    "",
    response_model=BusinessSpaceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_business_space(
    payload: BusinessSpaceCreate,
    user: CurrentUser,
    _csrf_session: CsrfSession,
    db: Database,
) -> BusinessSpaceResponse:
    try:
        business = BusinessSpaceService(db).create(payload, created_by=user.username)
    except ValueError as exc:
        if str(exc) == "business_name_exists":
            raise api_error(409, "business_name_exists", "Business name already exists") from exc
        raise
    return BusinessSpaceResponse.model_validate(business)


@router.get("/current", response_model=BusinessSpaceResponse)
def get_current_business_space(
    _user: CurrentUser,
    business: CurrentBusiness,
) -> BusinessSpaceResponse:
    return BusinessSpaceResponse.model_validate(business)


@router.get("/product-id-available")
def product_id_available(
    request: Request,
    db: Database,
    _user: CurrentUser,
    product_id: str = Query(min_length=1),
    business_id: str | None = Query(default=None),
) -> dict[str, bool]:
    service = SettingsService(
        SettingRepository(
            db,
            request.app.state.setting_cipher,
            request.app.state.settings.runner_setting_defaults(),
        )
    )
    return {"available": service.product_id_available(product_id, business_id)}


@router.patch("/{business_id}", response_model=BusinessSpaceResponse)
def update_business_space(
    business_id: str,
    payload: BusinessSpaceUpdate,
    _user: CurrentUser,
    _csrf_session: CsrfSession,
    db: Database,
) -> BusinessSpaceResponse:
    try:
        business = BusinessSpaceService(db).update(business_id, payload)
    except ValueError as exc:
        if str(exc) == "business_name_exists":
            raise api_error(409, "business_name_exists", "Business name already exists") from exc
        raise
    if business is None:
        raise api_error(404, "business_not_found", "Business space not found")
    return BusinessSpaceResponse.model_validate(business)


@router.post("/{business_id}/archive", response_model=BusinessSpaceResponse)
def archive_business_space(
    business_id: str,
    _user: CurrentUser,
    _csrf_session: CsrfSession,
    db: Database,
) -> BusinessSpaceResponse:
    try:
        business = BusinessSpaceService(db).archive(business_id)
    except ValueError as exc:
        if str(exc) == "default_business_cannot_archive":
            raise api_error(
                409,
                "default_business_cannot_archive",
                "Default business cannot be archived",
            ) from exc
        raise
    if business is None:
        raise api_error(404, "business_not_found", "Business space not found")
    return BusinessSpaceResponse.model_validate(business)
