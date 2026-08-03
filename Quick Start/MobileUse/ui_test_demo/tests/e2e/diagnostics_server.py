import os
from pathlib import Path

from mua_platform.diagnostics.mobile_use import RemotePodResult, RemoteProbeResult
from mua_platform.main import create_app
from mua_platform.pods.schemas import ListPodPage, PodSummary

if os.environ.get("APP_ENV") != "e2e":
    raise RuntimeError("diagnostics_server_requires_e2e_environment")


async def detail_busy_pod(_config):
    return RemotePodResult(
        pod_id="pod-loop3",
        status="busy",
        product_id="product-loop3",
        code="pod_unavailable",
        request_id="req-loop3-pod-busy",
    )


async def probe_mobile_use(_config):
    return RemoteProbeResult(
        ok=True,
        code="runner_api_reachable",
        request_id="req-loop3-probe-ok",
    )


def database_is_ready(_engine):
    return not Path(os.environ["E2E_NOT_READY_FILE"]).exists()


class DiagnosticsPodGateway:
    async def list_all(self, config) -> ListPodPage:
        return ListPodPage(
            items=(
                PodSummary(
                    product_id=config.product_id,
                    pod_id="pod-loop3",
                    pod_name="loop3-device",
                    pod_status_code=2,
                    stream_status=None,
                    image_id=None,
                    image_name=None,
                    aosp_version=None,
                    display_layout_id=None,
                    dc_id=None,
                    dc_name=None,
                    isp_code=None,
                    region=None,
                    zone_id=None,
                    config_code=None,
                    config_name=None,
                    config_type=None,
                    server_type_code=None,
                    intranet_ip=None,
                    adb_address=None,
                    adb_status=None,
                    data_size=None,
                    data_size_used=None,
                    pod_created_at=None,
                ),
            ),
            next_token=None,
            request_id="req-loop3-list",
        )


app = create_app(
    mobile_use_detail_pod=detail_busy_pod,
    mobile_use_probe_api=probe_mobile_use,
    pod_gateway=DiagnosticsPodGateway(),
    readiness_database_check=database_is_ready,
)
