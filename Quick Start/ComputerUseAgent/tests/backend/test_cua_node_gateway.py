from collections.abc import Mapping

import pytest

from mua_platform.pods.gateway import PodGateway
from mua_platform.runners.universal_gateway import UniversalRequest
from mua_platform.settings.schemas import RunnerConfig


def cua_config() -> RunnerConfig:
    return RunnerConfig(
        mode="mobile_use",
        access_key_id="ak",
        secret_access_key="sk",
        account_id="2103274899",
    )


def cua_node_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "Id": 133,
        "NodeId": 133,
        "Ecsid": "i-yeguephgqobw80d94vdf",
        "Name": "AI-OpenClaw-0LRt-000",
        "Provider": "volc_ecs",
        "Region": "cn-beijing",
        "ZoneId": "cn-beijing-a",
        "ProjectName": "default",
        "PrivateIp": "172.31.0.38",
        "PublicIp": "115.191.65.249",
        "OsType": "linux",
        "OsName": "Ubuntu 24.04 with OpenClaw 64 bit",
        "ImageId": "image-z0dpqndnmy8rpzcad9rz",
        "ImageName": "Ubuntu 24.04 with OpenClaw 64 bit",
        "InstanceType": "ecs.e-c1m2.xlarge",
        "Vcpu": 4,
        "MemoryGiB": 8,
        "Specification": "ecs.e-c1m2.xlarge 4vCPU 8GiB",
        "AgentEndpoint": "http://115.191.65.249:8910",
        "PluginVersion": "0.0.3",
        "ScriptVersion": "0.0.3",
        "Status": 4,
        "StatusName": "异常",
        "StatusMessage": "bootstrap failed",
        "LastHeartbeatAt": 0,
        "CreatedAt": 1784715750,
        "UpdatedAt": 1784715896,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_cua_node_gateway_lists_nodes_by_account_id():
    calls: list[UniversalRequest] = []

    def call(_config: RunnerConfig, request: UniversalRequest) -> Mapping[str, object]:
        calls.append(request)
        return {
            "ResponseMetadata": {"RequestId": "req-cua-list"},
            "Total": 1,
            "List": [cua_node_payload()],
        }

    page = await PodGateway(call=call).list_all(cua_config())

    assert [(item.service, item.action, item.version, item.method) for item in calls] == [
        ("ipaas", "ListCuaNode", "2023-08-01", "GET"),
    ]
    assert calls[0].body == {"AccountId": "2103274899"}
    assert page.request_id == "req-cua-list"
    assert len(page.items) == 1
    node = page.items[0]
    assert node.product_id == "2103274899"
    assert node.pod_id == "i-yeguephgqobw80d94vdf"
    assert node.pod_name == "AI-OpenClaw-0LRt-000"
    assert node.pod_status_code == 4
    assert node.image_id == "image-z0dpqndnmy8rpzcad9rz"
    assert node.image_name == "Ubuntu 24.04 with OpenClaw 64 bit"
    assert node.region == "cn-beijing"
    assert node.zone_id == "cn-beijing-a"
    assert node.intranet_ip == "172.31.0.38"
    assert node.eip_address == "115.191.65.249"
    assert node.server_type_code == "ecs.e-c1m2.xlarge"
    assert node.status_name == "异常"
    assert node.specification == "ecs.e-c1m2.xlarge 4vCPU 8GiB"
    assert node.agent_endpoint == "http://115.191.65.249:8910"


@pytest.mark.asyncio
async def test_cua_node_gateway_fetches_detail_with_get_cua_node():
    calls: list[UniversalRequest] = []

    def call(_config: RunnerConfig, request: UniversalRequest) -> Mapping[str, object]:
        calls.append(request)
        return {
            "ResponseMetadata": {"RequestId": "req-cua-detail"},
            "Result": cua_node_payload(
                Name="grafana",
                Ecsid="i-yemj9hi22oxjd1yy592l",
                PublicIp="124.174.97.147",
                PrivateIp="10.1.3.3",
                PluginVersion="0.0.5",
                ScriptVersion="0.0.5",
                Status=6,
                StatusName="升级失败",
            ),
        }

    detail = await PodGateway(call=call).detail(cua_config(), "i-yemj9hi22oxjd1yy592l")

    assert [(item.service, item.action, item.version, item.method) for item in calls] == [
        ("ipaas", "GetCuaNode", "2023-08-01", "GET"),
    ]
    assert calls[0].body == {
        "AccountId": "2103274899",
        "Ecsid": "i-yemj9hi22oxjd1yy592l",
    }
    assert detail.request_id == "req-cua-detail"
    assert detail.pod_name == "grafana"
    assert detail.pod_id == "i-yemj9hi22oxjd1yy592l"
    assert detail.provider == "volc_ecs"
    assert detail.public_ip == "124.174.97.147"
    assert detail.intranet_ip == "10.1.3.3"
    assert detail.plugin_version == "0.0.5"
    assert detail.script_version == "0.0.5"
    assert detail.status_name == "升级失败"
