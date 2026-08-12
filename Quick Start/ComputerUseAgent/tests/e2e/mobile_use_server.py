import os
from threading import Lock
from typing import Any

from cua_platform.diagnostics.mobile_use import RemotePodResult, RemoteProbeResult
from cua_platform.main import create_app
from cua_platform.pods.gateway import PodGateway
from cua_platform.runners import universal_gateway
from cua_platform.runners.universal_gateway import UniversalRemoteError, UniversalRequest

if os.environ.get("APP_ENV") != "e2e":
    raise RuntimeError("mobile_use_server_requires_e2e_environment")


SCENARIOS = {
    "Mobile通过": "pass",
    "Mobile结构非法": "invalid",
    "Mobile取消": "hold",
    "Loop5并发任务": "loop5",
    "Loop5结构非法": "invalid",
    "Loop5取消": "hold",
}

_lock = Lock()
_runs: dict[str, dict[str, Any]] = {}
_requests: list[UniversalRequest] = []
_loop5_detail_pods: set[str] = set()
_loop5_step_attempts: dict[str, int] = {}


def _metadata(action: str, request_id: str) -> dict[str, str]:
    return {
        "RequestId": request_id,
        "Action": action,
        "Version": "2023-08-01",
        "Service": "ipaas",
        "Region": "cn-north-1",
    }


def _scenario(request: UniversalRequest) -> str:
    run_name = str(request.body.get("RunName", ""))
    user_prompt = str(request.body.get("UserPrompt", ""))
    for title, scenario in SCENARIOS.items():
        if title in run_name or title in user_prompt:
            return scenario
    raise AssertionError("unknown_mobile_use_e2e_scenario")


def call_mobile_use(_config, request: UniversalRequest) -> dict[str, Any]:
    with _lock:
        _requests.append(request)
        if request.action == "ListPod":
            if _config.product_id == "product-loop5":
                return _loop5_list_pods(request)
            return {
                "ResponseMetadata": _metadata(request.action, "req-list-pod-e2e"),
                "Result": {
                    "Row": [
                        {
                            "ProductId": _config.product_id,
                            "PodId": "pod-e2e",
                            "PodName": "e2e-device",
                            "Online": 1,
                            "Status": "Running",
                        }
                    ],
                    "Total": 1,
                },
            }
        if request.action == "DetailPod":
            if _config.product_id == "product-loop5":
                return _loop5_detail_pod(request)
            return {
                "ResponseMetadata": _metadata(
                    request.action,
                    "req-detail-pod-e2e",
                ),
                "Result": {
                    "Row": [
                        {
                            "ProductId": _config.product_id,
                            "PodId": "pod-e2e",
                            "PodName": "e2e-device",
                            "Online": 1,
                            "Status": "Running",
                        }
                    ]
                },
            }
        if request.action == "RunAgentTaskOneStep":
            run_id = f"run-e2e-{len(_runs) + 1}"
            _runs[run_id] = {
                "scenario": _scenario(request),
                "cancelled": False,
                "request": request,
            }
            return {
                "ResponseMetadata": _metadata(request.action, f"req-start-{run_id}"),
                "Result": {"RunId": run_id},
            }

        run_id = str(request.body.get("RunId", ""))
        run = _runs[run_id]
        if request.action == "ListAgentRunCurrentStep":
            if run["scenario"] == "loop5":
                attempts = _loop5_step_attempts.get(run_id, 0) + 1
                _loop5_step_attempts[run_id] = attempts
                if attempts == 1:
                    raise UniversalRemoteError(
                        "remote_unavailable",
                        f"req-step-retry-{run_id}",
                        retryable=True,
                        response_received=False,
                    )
                action = "finished" if len(_loop5_detail_pods) >= 2 else "tap"
            else:
                action = (
                    "tap"
                    if run["scenario"] == "hold" and not run["cancelled"]
                    else "finished"
                )
            return {
                "ResponseMetadata": _metadata(request.action, f"req-step-{run_id}"),
                "Result": {
                    "Results": [
                        {
                            "Action": action,
                            "Param": {"x": 360, "y": 760},
                            "StepResult": {"Result": action},
                            "Timestamp": 1767225600000,
                        }
                    ]
                },
            }
        if request.action == "GetAgentResult":
            return _result(run_id, run)
        if request.action == "CancelTask":
            run["cancelled"] = True
            return {
                "ResponseMetadata": _metadata(request.action, f"req-cancel-{run_id}"),
                "Result": None,
            }
    raise AssertionError(f"unexpected_mobile_use_action:{request.action}")


def _result(run_id: str, run: dict[str, Any]) -> dict[str, Any]:
    request_id = (
        f"req-result-safe-{run_id}"
        if run["scenario"] == "loop5"
        else f"req-result-{run_id}"
    )
    metadata = _metadata("GetAgentResult", request_id)
    if run["cancelled"]:
        return {
            "ResponseMetadata": metadata,
            "Result": {"IsSuccess": 5, "Content": "用户取消"},
        }
    if run["scenario"] == "invalid":
        return {
            "ResponseMetadata": metadata,
            "Result": {"IsSuccess": 1, "Content": "任务看起来已经完成"},
        }
    return {
        "ResponseMetadata": metadata,
        "Result": {
            "IsSuccess": 1,
            "Content": "任务执行完成",
            "StructOutput": {
                "status": "pass",
                "reason": "首页已打开",
                "steps": [
                    {
                        "index": 1,
                        "status": "passed",
                        "log": "首页已打开；必须断言证据：页面出现首页",
                    }
                ],
                "assertions": [
                    {
                        "index": 1,
                        "result": "pass",
                        "evidence": ["页面出现首页"],
                    }
                ],
                "evidence": ["截图显示首页标题"],
            },
        },
    }


def _loop5_list_pods(request: UniversalRequest) -> dict[str, Any]:
    next_token = request.body.get("NextToken")
    pages = {
        None: (
            [
                _loop5_pod("pod-loop5-a", "loop5-alpha"),
                _loop5_pod("pod-loop5-b", "loop5-beta"),
            ],
            "loop5-page-2",
        ),
        "loop5-page-2": (
            [_loop5_pod("pod-loop5-c", "loop5-gamma")],
            None,
        ),
    }
    if next_token not in pages:
        raise AssertionError("unexpected_loop5_list_pod_token")
    rows, following_token = pages[next_token]
    return {
        "ResponseMetadata": _metadata(
            "ListPod",
            f"req-list-loop5-{next_token or 'first'}",
        ),
        "Result": {"Row": rows, "NextToken": following_token},
    }


def _loop5_detail_pod(request: UniversalRequest) -> dict[str, Any]:
    pod_id = str(request.body.get("PodId", ""))
    names = {
        "pod-loop5-a": "loop5-alpha",
        "pod-loop5-b": "loop5-beta",
        "pod-loop5-c": "loop5-gamma",
    }
    if pod_id not in names:
        raise AssertionError("unexpected_loop5_detail_pod")
    _loop5_detail_pods.add(pod_id)
    row = _loop5_pod(pod_id, names[pod_id])
    if pod_id == "pod-loop5-c":
        row.update({"Online": 0, "Status": "Offline"})
    return {
        "ResponseMetadata": _metadata("DetailPod", f"req-detail-{pod_id}"),
        "Result": {"Row": [row]},
    }


def _loop5_pod(pod_id: str, pod_name: str) -> dict[str, Any]:
    return {
        "ProductId": "product-loop5",
        "PodId": pod_id,
        "PodName": pod_name,
        "Online": 1,
        "Status": "Running",
    }


async def detail_available_pod(_config):
    return RemotePodResult(
        pod_id="pod-e2e",
        status="available",
        product_id="product-e2e",
        code="pod_available",
        request_id="req-e2e-pod",
    )


async def probe_mobile_use(_config):
    return RemoteProbeResult(
        ok=True,
        code="runner_api_reachable",
        request_id="req-e2e-probe",
    )


# create_app constructs the production gateway internally; replace only its SDK callable.
universal_gateway.call_universal = call_mobile_use
app = create_app(
    mobile_use_detail_pod=detail_available_pod,
    mobile_use_probe_api=probe_mobile_use,
    pod_gateway=PodGateway(call_mobile_use),
)
