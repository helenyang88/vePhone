import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from cua_platform.diagnostics.schemas import (
    PodDiagnostic,
    PodDiagnosticCode,
    PodStatus,
    ValidationCheck,
    ValidationResult,
)
from cua_platform.settings.schemas import RunnerConfig

_T = TypeVar("_T")
_SAFE_PROBE_CODES = {
    "credentials_invalid",
    "permission_denied",
    "runner_api_unreachable",
    "runner_api_unavailable",
    "request_rejected",
}
_SAFE_POD_CODES = _SAFE_PROBE_CODES | {
    "pod_not_found",
    "pod_unavailable",
}
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


@dataclass(frozen=True)
class RemotePodResult:
    pod_id: str
    status: PodStatus
    product_id: str
    code: PodDiagnosticCode
    request_id: str | None


@dataclass(frozen=True)
class RemoteProbeResult:
    ok: bool
    code: str
    request_id: str | None


class MobileUseDiagnosticGateway(Protocol):
    async def detail_pod(self, config: RunnerConfig) -> RemotePodResult: ...

    async def probe_api(self, config: RunnerConfig) -> RemoteProbeResult: ...


DiagnosticCall = Callable[[RunnerConfig], Awaitable[_T]]


class CallableMobileUseDiagnosticGateway:
    """Adapts injected control-plane SDK calls to the narrow diagnostic contract."""

    def __init__(
        self,
        detail_pod: DiagnosticCall[RemotePodResult],
        probe_api: DiagnosticCall[RemoteProbeResult],
    ) -> None:
        _require_async_callable("detail_pod", detail_pod)
        _require_async_callable("probe_api", probe_api)
        self._detail_pod = detail_pod
        self._probe_api = probe_api

    async def detail_pod(self, config: RunnerConfig) -> RemotePodResult:
        try:
            return await self._detail_pod(config)
        except Exception as exc:
            error = _safe_remote_error(exc, _SAFE_POD_CODES)
            if error is None:
                raise
            code, request_id = error
            return RemotePodResult(
                pod_id=config.pod_id or "unknown",
                status="unknown",
                product_id=config.product_id or "unknown",
                code=code,
                request_id=request_id,
            )

    async def probe_api(self, config: RunnerConfig) -> RemoteProbeResult:
        try:
            return await self._probe_api(config)
        except Exception as exc:
            error = _safe_remote_error(exc, _SAFE_PROBE_CODES)
            if error is None:
                raise
            code, request_id = error
            return RemoteProbeResult(ok=False, code=code, request_id=request_id)


class MobileUseDiagnosticAdapter:
    runner_type = "mobile_use"

    def __init__(self, gateway: MobileUseDiagnosticGateway) -> None:
        self._gateway = gateway

    async def validate(self, config: RunnerConfig) -> ValidationResult:
        probe = await self._gateway.probe_api(config)
        pod = await self._gateway.detail_pod(config)
        checks = (
            *_probe_checks(probe),
            _pod_check(pod),
        )
        return ValidationResult(
            runner_mode="mobile_use",
            status="passed" if all(check.status == "passed" for check in checks) else "failed",
            checks=checks,
        )

    async def list_pods(self, config: RunnerConfig) -> tuple[PodDiagnostic, ...]:
        pod = await self._gateway.detail_pod(config)
        return (
            PodDiagnostic(
                pod_id=pod.pod_id,
                status=pod.status,
                product_id=pod.product_id,
                code=pod.code,
                message=_pod_message(pod.status),
                request_id=pod.request_id,
            ),
        )


def _probe_checks(result: RemoteProbeResult) -> tuple[ValidationCheck, ValidationCheck]:
    if result.ok:
        return (
            ValidationCheck(
                name="credentials",
                status="passed",
                code="credentials_valid",
                message="凭证校验通过",
                request_id=result.request_id,
            ),
            ValidationCheck(
                name="runner_api",
                status="passed",
                code="runner_api_reachable",
                message="Runner API 可调用",
                request_id=result.request_id,
            ),
        )
    credentials_failed = result.code in {"credentials_invalid", "permission_denied"}
    return (
        ValidationCheck(
            name="credentials",
            status="failed" if credentials_failed else "passed",
            code="credentials_invalid" if credentials_failed else "credentials_valid",
            message="凭证校验失败" if credentials_failed else "凭证校验通过",
            request_id=result.request_id,
        ),
        ValidationCheck(
            name="runner_api",
            status="failed",
            code="runner_api_unreachable",
            message="Runner API 不可调用",
            request_id=result.request_id,
        ),
    )


def _pod_check(result: RemotePodResult) -> ValidationCheck:
    status = "passed" if result.status == "available" else "failed"
    return ValidationCheck(
        name="pod",
        status=status,
        code=result.code,
        message=_pod_message(result.status),
        request_id=result.request_id,
    )


def _pod_message(status: PodStatus) -> str:
    return {
        "available": "Pod 可用于执行",
        "busy": "Pod 正忙",
        "offline": "Pod 已离线",
        "unknown": "Pod 状态未知",
    }[status]


def _safe_remote_error(
    exc: Exception,
    allowed_codes: set[str],
) -> tuple[str, str | None] | None:
    code = getattr(exc, "code", None)
    if not isinstance(code, str) or code not in allowed_codes:
        return None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str) or _SAFE_REQUEST_ID.fullmatch(request_id) is None:
        request_id = None
    return code, request_id


def _require_async_callable(name: str, call: DiagnosticCall[_T]) -> None:
    call_method = getattr(call, "__call__", None)
    if not (
        inspect.iscoroutinefunction(call)
        or inspect.iscoroutinefunction(call_method)
    ):
        raise TypeError(f"{name}_must_be_async")
