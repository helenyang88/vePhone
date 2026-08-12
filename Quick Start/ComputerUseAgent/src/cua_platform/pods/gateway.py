from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from cua_platform.pods.schemas import ListPodPage, PodDetail, PodSummary
from cua_platform.runners.universal_gateway import (
    Sleep,
    UniversalCall,
    UniversalGateway,
    UniversalRemoteError,
    UniversalRequest,
    safe_request_id,
)
from cua_platform.settings.schemas import RunnerConfig

_SERVICE = "ipaas"
_VERSION = "2023-08-01"
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
        body: dict[str, Any] = {"AccountId": product_id}
        response = await self._gateway._invoke(
            config,
            UniversalRequest(
                service=_SERVICE,
                action="ListCuaNode",
                version=_VERSION,
                method="GET",
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
                action="GetCuaNode",
                version=_VERSION,
                method="GET",
                body={"AccountId": product_id, "Ecsid": pod_id},
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
            node_id=summary.node_id,
            provider=summary.provider,
            project_name=summary.project_name,
            public_ip=summary.public_ip,
            os_type=summary.os_type,
            os_name=summary.os_name,
            instance_type=summary.instance_type,
            vcpu=summary.vcpu,
            memory_gib=summary.memory_gib,
            specification=summary.specification,
            agent_endpoint=summary.agent_endpoint,
            plugin_version=summary.plugin_version,
            script_version=summary.script_version,
            status_name=summary.status_name,
            status_message=summary.status_message,
            last_heartbeat_at=summary.last_heartbeat_at,
            node_updated_at=summary.node_updated_at,
        )


def _parse_list_page(
    response: Mapping[str, Any],
    product_id: str,
) -> ListPodPage:
    request_id = _request_id(response)
    result = _extract_result(response, request_id)
    rows_raw = result.get("List")
    next_token = None
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
    if "Row" in response or "List" in response:
        return response
    raise _invalid_response(request_id)


def _extract_detail_result(
    response: Mapping[str, Any],
    request_id: str | None,
) -> Mapping[str, Any]:
    result = response.get("Result")
    if isinstance(result, Mapping):
        for key in ("Node", "Data", "CuaNode"):
            nested = result.get(key)
            if isinstance(nested, Mapping):
                return nested
        if "Ecsid" in result:
            return result
    if "Ecsid" in response:
        return response
    raise _invalid_response(request_id)


def _parse_pod_dict(
    value: Any,
    product_id: str,
    request_id: str | None,
) -> PodSummary:
    if not isinstance(value, Mapping):
        raise _invalid_response(request_id)
    pod_id = _opt_str(value, "Ecsid")
    pod_name = _opt_str(value, "Name")
    if not pod_id or not pod_name:
        raise _invalid_response(request_id)

    pod_status_code = _opt_int(value, "Status")
    if pod_status_code is None:
        raise _invalid_response(request_id)

    stream_status = None

    image_id = _opt_str(value, "ImageId")
    image_name = _opt_str(value, "ImageName") or _opt_str(value, "OsName")
    aosp_version = None
    display_layout_id = None
    intranet_ip = _opt_str(value, "PrivateIp")
    adb_address = None
    adb_status = None
    data_size = None
    data_size_used = None
    server_type_code = _opt_str(value, "InstanceType")

    create_at_ts = _opt_int(value, "CreatedAt")
    pod_created_at: datetime | None = None
    if create_at_ts is not None and create_at_ts > 0:
        pod_created_at = datetime.fromtimestamp(create_at_ts, tz=timezone.utc)

    updated_at_ts = _opt_int(value, "UpdatedAt")
    node_updated_at: datetime | None = None
    if updated_at_ts is not None and updated_at_ts > 0:
        node_updated_at = datetime.fromtimestamp(updated_at_ts, tz=timezone.utc)

    heartbeat_ts = _opt_int(value, "LastHeartbeatAt")
    last_heartbeat_at: datetime | None = None
    if heartbeat_ts is not None and heartbeat_ts > 0:
        last_heartbeat_at = datetime.fromtimestamp(heartbeat_ts, tz=timezone.utc)

    dc_id = dc_name = None
    region = _opt_str(value, "Region")
    zone_id = _opt_str(value, "ZoneId")
    isp_code: int | None = None
    config_code = _opt_str(value, "InstanceType")
    config_name = _opt_str(value, "Specification")
    config_type: int | None = None
    eip_address = _opt_str(value, "PublicIp")

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
        node_id=_opt_int(value, "NodeId") or _opt_int(value, "Id"),
        provider=_opt_str(value, "Provider"),
        project_name=_opt_str(value, "ProjectName"),
        public_ip=_opt_str(value, "PublicIp"),
        os_type=_opt_str(value, "OsType"),
        os_name=_opt_str(value, "OsName"),
        instance_type=_opt_str(value, "InstanceType"),
        vcpu=_opt_int(value, "Vcpu"),
        memory_gib=_opt_int(value, "MemoryGiB"),
        specification=_opt_str(value, "Specification"),
        agent_endpoint=_opt_str(value, "AgentEndpoint"),
        plugin_version=_opt_str(value, "PluginVersion"),
        script_version=_opt_str(value, "ScriptVersion"),
        status_name=_opt_str(value, "StatusName"),
        status_message=_opt_str(value, "StatusMessage"),
        last_heartbeat_at=last_heartbeat_at,
        node_updated_at=node_updated_at,
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
    if not config.account_id:
        raise ValueError("pod_pool_settings_incomplete")
    return config.account_id


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
