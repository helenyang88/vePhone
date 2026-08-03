from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from mua_platform.pods.schemas import ListPodPage, PodDetail, PodSummary
from mua_platform.runners.universal_gateway import (
    Sleep,
    UniversalCall,
    UniversalGateway,
    UniversalRemoteError,
    UniversalRequest,
    safe_request_id,
)
from mua_platform.settings.schemas import RunnerConfig

_SERVICE = "ACEP"
_VERSION = "2025-05-01"
_MAX_PODS = 10_000
_PAGE_SIZE = 100


class PodGateway:
    def __init__(
        self,
        call: UniversalCall | None = None,
        *,
        sleep: Sleep | None = None,
    ) -> None:
        kwargs = {} if sleep is None else {"sleep": sleep}
        self._gateway = UniversalGateway(call, **kwargs)

    async def list_all(self, config: RunnerConfig) -> ListPodPage:
        items: list[PodSummary] = []
        seen: set[str] = set()
        next_token: str | None = None
        request_id: str | None = None
        page_count = 0
        while True:
            page = await self._list_page(config, next_token=next_token)
            request_id = page.request_id or request_id
            for item in page.items:
                if item.pod_id in seen:
                    raise _invalid_response(page.request_id)
                seen.add(item.pod_id)
                items.append(item)
            page_count += 1
            if page.next_token is None or page.next_token == "":
                break
            if page_count > 200:
                raise _invalid_response(request_id)
            next_token = page.next_token
        if len(items) > _MAX_PODS:
            raise _invalid_response(request_id)
        return ListPodPage(tuple(items), None, request_id)

    async def _list_page(
        self,
        config: RunnerConfig,
        *,
        next_token: str | None = None,
    ) -> ListPodPage:
        product_id = _product_id(config)
        body: dict[str, Any] = {"ProductId": product_id, "MaxResults": _PAGE_SIZE}
        if next_token:
            body["NextToken"] = next_token
        response = await self._gateway._invoke(
            config,
            UniversalRequest(
                service=_SERVICE,
                action="ListPod",
                version=_VERSION,
                method="POST",
                body=body,
            ),
            retry_get=False,
            trace_key=None,
        )
        return _parse_list_page(response, product_id)

    async def detail(self, config: RunnerConfig, pod_id: str) -> PodDetail:
        product_id = _product_id(config)
        if not isinstance(pod_id, str) or not pod_id:
            raise ValueError("pod_id_invalid")
        response = await self._gateway.invoke_read(
            config,
            UniversalRequest(
                service=_SERVICE,
                action="DetailPod",
                version=_VERSION,
                method="GET",
                body={"ProductId": product_id, "PodId": pod_id},
            ),
        )
        request_id = _request_id(response)
        result = _extract_detail_result(response, request_id)
        summary = _parse_pod_dict(result, product_id, request_id)
        if summary.pod_id != pod_id:
            raise _invalid_response(request_id)
        return PodDetail(
            product_id=summary.product_id,
            pod_id=summary.pod_id,
            pod_name=summary.pod_name,
            pod_status_code=summary.pod_status_code,
            stream_status=summary.stream_status,
            image_id=summary.image_id,
            image_name=summary.image_name,
            aosp_version=summary.aosp_version,
            display_layout_id=summary.display_layout_id,
            dc_id=summary.dc_id,
            dc_name=summary.dc_name,
            isp_code=summary.isp_code,
            region=summary.region,
            zone_id=summary.zone_id,
            config_code=summary.config_code,
            config_name=summary.config_name,
            config_type=summary.config_type,
            server_type_code=summary.server_type_code,
            intranet_ip=summary.intranet_ip,
            adb_address=summary.adb_address,
            adb_status=summary.adb_status,
            data_size=summary.data_size,
            data_size_used=summary.data_size_used,
            pod_created_at=summary.pod_created_at,
            request_id=request_id,
            eip_address=summary.eip_address,
        )


def _parse_list_page(
    response: Mapping[str, Any],
    product_id: str,
) -> ListPodPage:
    request_id = _request_id(response)
    result = _extract_result(response, request_id)
    rows_raw = result.get("Row")
    next_token = result.get("NextToken")
    if not isinstance(rows_raw, list):
        raise _invalid_response(request_id)
    if len(rows_raw) > _PAGE_SIZE:
        raise _invalid_response(request_id)
    items = tuple(_parse_pod_dict(row, product_id, request_id) for row in rows_raw)
    if len({item.pod_id for item in items}) != len(items):
        raise _invalid_response(request_id)
    token: str | None
    if isinstance(next_token, str) and next_token:
        token = next_token
    else:
        token = None
    return ListPodPage(items=items, next_token=token, request_id=request_id)


def _extract_result(
    response: Mapping[str, Any],
    request_id: str | None,
) -> Mapping[str, Any]:
    result = response.get("Result")
    if isinstance(result, Mapping):
        return result
    if "Row" in response:
        return response
    raise _invalid_response(request_id)


def _extract_detail_result(
    response: Mapping[str, Any],
    request_id: str | None,
) -> Mapping[str, Any]:
    result = response.get("Result")
    if isinstance(result, Mapping):
        rows = result.get("Row")
        if isinstance(rows, list):
            if len(rows) != 1 or not isinstance(rows[0], Mapping):
                raise _invalid_response(request_id)
            return rows[0]
        if "PodId" in result:
            return result
    if "PodId" in response:
        return response
    raise _invalid_response(request_id)


def _parse_pod_dict(
    value: Any,
    product_id: str,
    request_id: str | None,
) -> PodSummary:
    if not isinstance(value, Mapping):
        raise _invalid_response(request_id)
    row_product_id = _opt_str(value, "ProductId")
    pod_id = _opt_str(value, "PodId")
    pod_name = _opt_str(value, "PodName")
    if row_product_id != product_id or not pod_id or not pod_name:
        raise _invalid_response(request_id)

    pod_status_code = _opt_int(value, "Online")
    if pod_status_code is None or pod_status_code not in (0, 1, 2, 3, 4):
        raise _invalid_response(request_id)

    stream_status = _opt_int(value, "StreamStatus")

    image_id = _opt_str(value, "ImageId")
    image_name = _opt_str(value, "ImageName")
    aosp_version = _opt_str(value, "AospVersion")
    display_layout_id = _opt_str(value, "DisplayLayoutId")
    intranet_ip = _opt_str(value, "IntranetIP")
    adb_address = _opt_str(value, "Adb")
    adb_status = _opt_int(value, "AdbStatus")
    data_size = _opt_str(value, "DataSize")
    data_size_used = _opt_str(value, "DataSizeUsed")
    server_type_code = _opt_str(value, "ServerTypeCode")

    create_at_ts = _opt_int(value, "CreateAt")
    pod_created_at: datetime | None = None
    if create_at_ts is not None and create_at_ts > 0:
        pod_created_at = datetime.fromtimestamp(create_at_ts, tz=timezone.utc)

    dc_info = value.get("DcInfo")
    dc_id = dc_name = region = zone_id = None
    isp_code: int | None = None
    if isinstance(dc_info, Mapping):
        dc_id = _opt_str(dc_info, "Dc")
        dc_name = _opt_str(dc_info, "DcName")
        region = _opt_str(dc_info, "Region")
        zone_id = _opt_str(dc_info, "ZoneId")
        isp_code = _opt_int(dc_info, "Isp")

    config = value.get("Configuration")
    config_code = config_name = None
    config_type: int | None = None
    if isinstance(config, Mapping):
        config_code = _opt_str(config, "ConfigurationCode")
        config_name = _opt_str(config, "ConfigurationName")
        config_type = _opt_int(config, "ConfigurationType")
        if not server_type_code:
            server_type_code = _opt_str(config, "ServerTypeCode")

    eip_address: str | None = None
    eip = value.get("Eip")
    if isinstance(eip, Mapping):
        eip_address = _opt_str(eip, "EipAddress")

    return PodSummary(
        product_id=product_id,
        pod_id=pod_id,
        pod_name=pod_name,
        pod_status_code=pod_status_code,
        stream_status=stream_status,
        image_id=image_id,
        image_name=image_name,
        aosp_version=aosp_version,
        display_layout_id=display_layout_id,
        dc_id=dc_id,
        dc_name=dc_name,
        isp_code=isp_code,
        region=region,
        zone_id=zone_id,
        config_code=config_code,
        config_name=config_name,
        config_type=config_type,
        server_type_code=server_type_code,
        intranet_ip=intranet_ip,
        adb_address=adb_address,
        adb_status=adb_status,
        data_size=data_size,
        data_size_used=data_size_used,
        pod_created_at=pod_created_at,
        eip_address=eip_address,
    )


def _opt_str(value: Mapping[str, Any], key: str) -> str | None:
    v = value.get(key)
    return v if isinstance(v, str) and v else None


def _opt_int(value: Mapping[str, Any], key: str) -> int | None:
    v = value.get(key)
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return None


def _product_id(config: RunnerConfig) -> str:
    if not config.product_id:
        raise ValueError("pod_pool_settings_incomplete")
    return config.product_id


def _request_id(response: Mapping[str, Any]) -> str | None:
    metadata = response.get("ResponseMetadata")
    if not isinstance(metadata, Mapping):
        return None
    return safe_request_id(metadata.get("RequestId"))


def _invalid_response(request_id: str | None) -> UniversalRemoteError:
    return UniversalRemoteError(
        "response_invalid",
        request_id,
        retryable=False,
        response_received=True,
    )
