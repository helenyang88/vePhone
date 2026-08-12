import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from cua_platform.diagnostics.mobile_use import (
    CallableMobileUseDiagnosticGateway,
    MobileUseDiagnosticAdapter,
    RemotePodResult,
    RemoteProbeResult,
)
from cua_platform.diagnostics.schemas import PodDiagnostic, ValidationCheck
from cua_platform.diagnostics.service import DiagnosticsService
from cua_platform.runners.mock import MockRunner
from cua_platform.settings.schemas import RunnerConfig
from cua_platform.time import FakeClock


@pytest.mark.asyncio
async def test_mock_diagnostics_are_deterministic():
    runner = MockRunner("x" * 32)
    config = RunnerConfig.mock()

    validation = await runner.validate(config)
    pods = await runner.list_pods(config)

    assert validation.status == "passed"
    assert [check.name for check in validation.checks] == [
        "credentials",
        "runner_api",
        "pod",
    ]
    assert pods == (
        PodDiagnostic(
            pod_id="mock:default",
            status="available",
            product_id="mock:default",
            code="pod_available",
            message="Mock Pod 可用于执行",
            request_id=None,
        ),
    )


def test_diagnostic_dtos_are_frozen():
    check = ValidationCheck(
        name="runner_api",
        status="passed",
        code="ok",
        message="Runner API is available",
        request_id=None,
    )

    with pytest.raises(FrozenInstanceError):
        check.status = "failed"


class StubGateway:
    def __init__(
        self,
        probe: RemoteProbeResult,
        pod: RemotePodResult,
    ) -> None:
        self.probe = probe
        self.pod = pod
        self.calls: list[str] = []

    async def probe_api(self, _config: RunnerConfig) -> RemoteProbeResult:
        self.calls.append("probe_api")
        return self.probe

    async def detail_pod(self, _config: RunnerConfig) -> RemotePodResult:
        self.calls.append("detail_pod")
        return self.pod


@pytest.mark.asyncio
async def test_mobile_use_adapter_only_maps_typed_gateway_results():
    gateway = StubGateway(
        RemoteProbeResult(ok=False, code="permission_denied", request_id="remote_req_1"),
        RemotePodResult(
            pod_id="pod-safe",
            status="busy",
            product_id="product-safe",
            code="pod_unavailable",
            request_id="remote_req_2",
        ),
    )
    adapter = MobileUseDiagnosticAdapter(gateway)
    config = _mobile_use_config()

    validation = await adapter.validate(config)
    pods = await adapter.list_pods(config)

    assert gateway.calls == ["probe_api", "detail_pod", "detail_pod"]
    assert validation.status == "failed"
    assert validation.checks == (
        ValidationCheck(
            name="credentials",
            status="failed",
            code="credentials_invalid",
            message="凭证校验失败",
            request_id="remote_req_1",
        ),
        ValidationCheck(
            name="runner_api",
            status="failed",
            code="runner_api_unreachable",
            message="Runner API 不可调用",
            request_id="remote_req_1",
        ),
        ValidationCheck(
            name="pod",
            status="failed",
            code="pod_unavailable",
            message="Pod 正忙",
            request_id="remote_req_2",
        ),
    )
    assert pods == (
        PodDiagnostic(
            pod_id="pod-safe",
            status="busy",
            product_id="product-safe",
            code="pod_unavailable",
            message="Pod 正忙",
            request_id="remote_req_2",
        ),
    )


class RemoteCallError(RuntimeError):
    def __init__(self, message: str, *, code: str, request_id: str) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


@pytest.mark.asyncio
async def test_callable_gateway_extracts_only_safe_remote_error_fields():
    async def fail(_config: RunnerConfig):
        raise RemoteCallError(
            "AKLT-SENSITIVE SK-SENSITIVE",
            code="permission_denied",
            request_id="remote_req_safe",
        )

    gateway = CallableMobileUseDiagnosticGateway(fail, fail)
    config = _mobile_use_config()

    probe = await gateway.probe_api(config)
    pod = await gateway.detail_pod(config)

    assert probe == RemoteProbeResult(
        ok=False,
        code="permission_denied",
        request_id="remote_req_safe",
    )
    assert pod == RemotePodResult(
        pod_id="pod-safe",
        status="unknown",
        product_id="product-safe",
        code="permission_denied",
        request_id="remote_req_safe",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["pod_not_found", "pod_unavailable"])
async def test_callable_gateway_preserves_request_id_for_allowlisted_pod_errors(code):
    async def fail_pod(_config: RunnerConfig):
        raise RemoteCallError(
            "sensitive remote response",
            code=code,
            request_id="remote_req_pod_safe",
        )

    async def probe_ok(_config: RunnerConfig) -> RemoteProbeResult:
        return RemoteProbeResult(ok=True, code="runner_api_reachable", request_id=None)

    gateway = CallableMobileUseDiagnosticGateway(fail_pod, probe_ok)

    pod = await gateway.detail_pod(_mobile_use_config())

    assert pod == RemotePodResult(
        pod_id="pod-safe",
        status="unknown",
        product_id="product-safe",
        code=code,
        request_id="remote_req_pod_safe",
    )
    pods = await MobileUseDiagnosticAdapter(gateway).list_pods(
        _mobile_use_config()
    )
    assert pods == (
        PodDiagnostic(
            pod_id="pod-safe",
            status="unknown",
            product_id="product-safe",
            code=code,
            message="Pod 状态未知",
            request_id="remote_req_pod_safe",
        ),
    )


@pytest.mark.asyncio
async def test_runner_validation_preserves_pod_not_found_code():
    gateway = StubGateway(
        RemoteProbeResult(
            ok=True,
            code="runner_api_reachable",
            request_id="remote_req_probe",
        ),
        RemotePodResult(
            pod_id="pod-safe",
            status="unknown",
            product_id="product-safe",
            code="pod_not_found",
            request_id="remote_req_pod_missing",
        ),
    )

    result = await MobileUseDiagnosticAdapter(gateway).validate(
        _mobile_use_config()
    )

    assert result.checks[-1] == ValidationCheck(
        name="pod",
        status="failed",
        code="pod_not_found",
        message="Pod 状态未知",
        request_id="remote_req_pod_missing",
    )


@pytest.mark.parametrize("sync_position", ["detail_pod", "probe_api"])
def test_callable_gateway_rejects_sync_callables_without_invoking_them(sync_position):
    invoked = False

    def sync_call(_config: RunnerConfig):
        nonlocal invoked
        invoked = True
        raise AssertionError("sync callable must not run")

    async def async_detail(_config: RunnerConfig) -> RemotePodResult:
        return RemotePodResult(
            pod_id="pod-safe",
            status="available",
            product_id="product-safe",
            code="pod_available",
            request_id=None,
        )

    async def async_probe(_config: RunnerConfig) -> RemoteProbeResult:
        return RemoteProbeResult(ok=True, code="ok", request_id=None)

    calls = {
        "detail_pod": async_detail,
        "probe_api": async_probe,
    }
    calls[sync_position] = sync_call

    with pytest.raises(TypeError, match=f"{sync_position}_must_be_async"):
        CallableMobileUseDiagnosticGateway(
            calls["detail_pod"],
            calls["probe_api"],
        )

    assert invoked is False


@pytest.mark.asyncio
async def test_async_gateway_call_is_cancelled_by_service_timeout():
    probe_started = asyncio.Event()
    probe_cancelled = asyncio.Event()

    async def detail_pod(_config: RunnerConfig) -> RemotePodResult:
        raise AssertionError("detail_pod must not run after probe timeout")

    async def probe_api(_config: RunnerConfig) -> RemoteProbeResult:
        probe_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            probe_cancelled.set()

    config = _mobile_use_config()
    gateway = CallableMobileUseDiagnosticGateway(detail_pod, probe_api)
    service = DiagnosticsService(
        StaticSettingsService(config),
        lambda _config: MobileUseDiagnosticAdapter(gateway),
        FakeClock(datetime.fromisoformat("2026-07-25T08:00:00+00:00")),
        timeout_seconds=0.001,
    )

    result = await service.validate_runner()

    assert probe_started.is_set()
    assert probe_cancelled.is_set()
    assert result.status == "failed"
    assert result.checks[0].code == "diagnostic_timeout"


class StaticSettingsService:
    def __init__(self, config: RunnerConfig) -> None:
        self.config = config

    def get_runner_config(self) -> RunnerConfig:
        return self.config


class RaisingAdapter:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def validate(self, _config: RunnerConfig):
        if isinstance(self.error, TimeoutError):
            await asyncio.Event().wait()
        raise self.error

    async def list_pods(self, _config: RunnerConfig):
        if isinstance(self.error, TimeoutError):
            await asyncio.Event().wait()
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (TimeoutError(), "diagnostic_timeout"),
        (RuntimeError("secret-error-text"), "diagnostic_internal_error"),
    ],
)
async def test_service_normalizes_validation_failures(error, expected_code, caplog):
    config = _mobile_use_config()
    service = DiagnosticsService(
        StaticSettingsService(config),
        lambda _config: RaisingAdapter(error),
        FakeClock(datetime.fromisoformat("2026-07-25T08:00:00+00:00")),
        timeout_seconds=0.001,
    )

    result = await service.validate_runner()

    assert result.status == "failed"
    assert result.checks == (
        ValidationCheck(
            name="runner_api",
            status="failed",
            code=expected_code,
            message=(
                "Runner diagnostic timed out"
                if expected_code == "diagnostic_timeout"
                else "Runner diagnostic failed"
            ),
            request_id=None,
        ),
    )
    assert "secret-error-text" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (TimeoutError(), "Pod diagnostic timed out"),
        (RuntimeError("secret-error-text"), "Pod diagnostic failed"),
    ],
)
async def test_service_normalizes_pod_failures(error, expected_message, caplog):
    config = _mobile_use_config()
    service = DiagnosticsService(
        StaticSettingsService(config),
        lambda _config: RaisingAdapter(error),
        FakeClock(datetime.fromisoformat("2026-07-25T08:00:00+00:00")),
        timeout_seconds=0.001,
    )

    result = await service.list_pods()

    assert result == (
        PodDiagnostic(
            pod_id="pod-safe",
            status="unknown",
            product_id="product-safe",
            code=(
                "diagnostic_timeout"
                if expected_message == "Pod diagnostic timed out"
                else "diagnostic_internal_error"
            ),
            message=expected_message,
            request_id=None,
        ),
    )
    assert "secret-error-text" not in caplog.text


def _mobile_use_config() -> RunnerConfig:
    return RunnerConfig(
        mode="mobile_use",
        access_key_id="access-key-safe",
        secret_access_key="secret-key-sensitive",
        account_id="2103274899",
        product_id="product-safe",
        pod_id="pod-safe",
    )
