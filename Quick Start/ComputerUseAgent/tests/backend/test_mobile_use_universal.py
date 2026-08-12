import sys
from types import SimpleNamespace

import pytest

from cua_platform.diagnostics import universal as diagnostic_universal
from cua_platform.diagnostics.mobile_use import RemotePodResult, RemoteProbeResult
from cua_platform.diagnostics.universal import UniversalMobileUseClient
from cua_platform.runners.universal_gateway import (
    UniversalRemoteError,
    UniversalRequest,
)
from cua_platform.settings.schemas import RunnerConfig


@pytest.mark.asyncio
async def test_universal_client_uses_only_readonly_detail_pod_for_detail_and_probe():
    assert diagnostic_universal.UniversalRequest is UniversalRequest
    assert diagnostic_universal.UniversalRemoteError is UniversalRemoteError
    requests: list[UniversalRequest] = []

    def call(_config: RunnerConfig, request: UniversalRequest) -> dict:
        requests.append(request)
        return {
            "ResponseMetadata": {"RequestId": "remote_req_detail"},
            "Result": {
                "Row": [
                    {
                        "PodId": "pod-safe",
                        "Online": 1,
                    }
                ],
                "Total": 1,
            },
        }

    client = UniversalMobileUseClient(call=call)
    config = RunnerConfig(
        mode="mobile_use",
        access_key_id="access-key-safe",
        secret_access_key="secret-key-sensitive",
        product_id="product-safe",
        pod_id="pod-safe",
    )

    pod = await client.detail_pod(config)
    probe = await client.probe_api(config)

    assert pod == RemotePodResult(
        pod_id="pod-safe",
        status="available",
        product_id="product-safe",
        code="pod_available",
        request_id="remote_req_detail",
    )
    assert probe == RemoteProbeResult(
        ok=True,
        code="runner_api_reachable",
        request_id="remote_req_detail",
    )
    assert requests == [
        UniversalRequest(
            service="ACEP",
            action="DetailPod",
            version="2023-10-30",
            method="GET",
            body={"ProductId": "product-safe", "PodId": "pod-safe"},
        ),
        UniversalRequest(
            service="ACEP",
            action="DetailPod",
            version="2023-10-30",
            method="GET",
            body={"ProductId": "product-safe", "PodId": "pod-safe"},
        ),
    ]


@pytest.mark.asyncio
async def test_default_universal_call_uses_official_sdk_detail_pod_contract(monkeypatch):
    calls: list[tuple[object, dict[str, str]]] = []
    configurations: list[object] = []

    class Configuration:
        ak: str
        sk: str
        region: str

        def __init__(self) -> None:
            self.auto_retry = True
            configurations.append(self)

    class Flatten:
        def __init__(self, body: dict[str, str]) -> None:
            self.body = body

        def flat(self) -> dict[str, str]:
            return self.body

    class UniversalApi:
        def __init__(self, _client: object) -> None:
            pass

        def do_call(self, info: object, body: dict[str, str]) -> dict:
            calls.append((info, body))
            return {
                "ResponseMetadata": {"RequestId": "remote_req_sdk"},
                "Result": {"Row": [{"PodId": "pod-safe", "Online": 1}]},
            }

    fake_sdk = SimpleNamespace(
        Configuration=Configuration,
        ApiClient=lambda configuration: configuration,
        UniversalApi=UniversalApi,
        UniversalInfo=lambda **kwargs: SimpleNamespace(**kwargs),
        Flatten=Flatten,
    )
    monkeypatch.setitem(sys.modules, "volcenginesdkcore", fake_sdk)
    config = RunnerConfig(
        mode="mobile_use",
        access_key_id="access-key-safe",
        secret_access_key="secret-key-sensitive",
        product_id="product-safe",
        pod_id="pod-safe",
    )

    result = await UniversalMobileUseClient().detail_pod(config)

    assert result.request_id == "remote_req_sdk"
    assert len(calls) == 1
    info, body = calls[0]
    assert vars(info) == {
        "method": "GET",
        "action": "DetailPod",
        "service": "ACEP",
        "version": "2023-10-30",
        "content_type": "application/json",
    }
    assert configurations[0].auto_retry is False
    assert body == {"ProductId": "product-safe", "PodId": "pod-safe"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_id", "expected"),
    [
        ("remote_req_safe", "remote_req_safe"),
        ("unsafe request id", None),
    ],
)
async def test_probe_filters_request_id_from_allowlisted_pod_errors(
    request_id,
    expected,
):
    def fail(_config: RunnerConfig, _request: UniversalRequest) -> dict:
        raise UniversalRemoteError(
            "pod_not_found",
            request_id,
            retryable=False,
            response_received=True,
        )

    config = RunnerConfig(
        mode="mobile_use",
        access_key_id="access-key-safe",
        secret_access_key="secret-key-sensitive",
        product_id="product-safe",
        pod_id="pod-safe",
    )

    result = await UniversalMobileUseClient(call=fail).probe_api(config)

    assert result == RemoteProbeResult(
        ok=True,
        code="runner_api_reachable",
        request_id=expected,
    )
