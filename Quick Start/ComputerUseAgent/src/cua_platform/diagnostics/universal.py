import asyncio
from collections.abc import Mapping
from typing import Any

from cua_platform.diagnostics.mobile_use import RemotePodResult, RemoteProbeResult
from cua_platform.runners.universal_gateway import (
    UniversalCall,
    UniversalRemoteError,
    UniversalRequest,
    call_universal,
    safe_request_id,
)
from cua_platform.settings.schemas import RunnerConfig


_DETAIL_POD = UniversalRequest(
    service="ACEP",
    action="DetailPod",
    version="2023-10-30",
    method="GET",
    body={},
)
_POD_ERROR_CODES = {"pod_not_found", "pod_unavailable"}


class UniversalMobileUseClient:
    def __init__(self, call: UniversalCall | None = None) -> None:
        self._call = call or call_universal

    async def detail_pod(self, config: RunnerConfig) -> RemotePodResult:
        request = _detail_pod_request(config)
        response = await asyncio.to_thread(self._call, config, request)
        metadata = _mapping(response.get("ResponseMetadata"))
        result = _mapping(response.get("Result"))
        rows = result.get("Row")
        row = _mapping(rows[0]) if isinstance(rows, list) and rows else result
        status = _pod_status(row.get("Online", row.get("online")))
        return RemotePodResult(
            pod_id=_string(row.get("PodId") or row.get("pod_id"), config.pod_id),
            status=status,
            product_id=_string(
                row.get("ProductId") or row.get("product_id"),
                config.product_id,
            ),
            code="pod_available" if status == "available" else "pod_unavailable",
            request_id=safe_request_id(
                metadata.get("RequestId") or metadata.get("request_id")
            ),
        )

    async def probe_api(self, config: RunnerConfig) -> RemoteProbeResult:
        try:
            pod = await self.detail_pod(config)
        except UniversalRemoteError as exc:
            if exc.code not in _POD_ERROR_CODES:
                raise
            return RemoteProbeResult(
                ok=True,
                code="runner_api_reachable",
                request_id=safe_request_id(exc.request_id),
            )
        return RemoteProbeResult(
            ok=True,
            code="runner_api_reachable",
            request_id=pod.request_id,
        )


def _detail_pod_request(config: RunnerConfig) -> UniversalRequest:
    if not config.product_id or not config.pod_id:
        raise ValueError("mobile_use_detail_pod_config_incomplete")
    return UniversalRequest(
        service=_DETAIL_POD.service,
        action=_DETAIL_POD.action,
        version=_DETAIL_POD.version,
        method=_DETAIL_POD.method,
        body={"ProductId": config.product_id, "PodId": config.pod_id},
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: Any, fallback: str | None) -> str:
    return value if isinstance(value, str) and value else fallback or "unknown"


def _pod_status(value: Any) -> str:
    if value == 1:
        return "available"
    if value == 2:
        return "offline"
    if value in {0, 3, 4}:
        return "busy"
    return "unknown"
