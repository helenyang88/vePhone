from datetime import UTC, datetime

from mua_platform.pods.models import DiscoveredPod


MOBILE_USE_STREAM_CONFIG = {
    "access_key_id": "AKLT00000000WXYZ",
    "secret_access_key": "long-term-secret-value",
    "product_id": "prod_123",
    "account_id": "2100000000000000000",
    "sts_role_trn": "trn:iam::2100000000000000000:role/mua-stream-viewer",
}


class FakeStreamTokenGateway:
    def __init__(self):
        self.calls = []

    async def assume_role(self, config, *, pod_id: str, user_id: str):
        self.calls.append(
            {
                "account_id": config.account_id,
                "product_id": config.product_id,
                "pod_id": pod_id,
                "role_trn": config.sts_role_trn,
                "ttl": config.stream_token_ttl_seconds,
                "user_id": user_id,
            }
        )
        return {
            "AccessKeyID": "AKTP_TEMP",
            "SecretAccessKey": "temporary-secret",
            "SessionToken": "session-token",
            "CurrentTime": "2026-08-03T10:00:00+08:00",
            "ExpiredTime": "2026-08-03T10:10:00+08:00",
        }


def _add_pod(client, *, product_id: str = "prod_123", pod_id: str = "pod_123") -> None:
    with client.app.state.session_factory() as db:
        db.add(
            DiscoveredPod(
                id=f"{product_id}:{pod_id}",
                product_id=product_id,
                pod_id=pod_id,
                pod_name="测试云机",
                pod_status_code=1,
                stream_status=2,
                discovery_state="active",
                last_seen_at=datetime.now(UTC),
            )
        )
        db.commit()


def test_pod_stream_session_returns_web_sdk_start_config(authenticated_client):
    gateway = FakeStreamTokenGateway()
    authenticated_client.app.state.stream_token_gateway = gateway
    _add_pod(authenticated_client)
    configured = authenticated_client.put(
        "/api/v1/settings/runner",
        json={"mode": "mobile_use", "mobile_use": MOBILE_USE_STREAM_CONFIG},
    )
    assert configured.status_code == 200

    response = authenticated_client.post("/api/v1/pod-pool/pod_123/stream-session")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "account_id": "2100000000000000000",
        "product_id": "prod_123",
        "pod_id": "pod_123",
        "user_id": "mua-admin",
        "token": {
            "AccessKeyID": "AKTP_TEMP",
            "SecretAccessKey": "temporary-secret",
            "SessionToken": "session-token",
            "CurrentTime": "2026-08-03T10:00:00+08:00",
            "ExpiredTime": "2026-08-03T10:10:00+08:00",
        },
    }
    assert gateway.calls == [
        {
            "account_id": "2100000000000000000",
            "product_id": "prod_123",
            "pod_id": "pod_123",
            "role_trn": "trn:iam::2100000000000000000:role/mua-stream-viewer",
            "ttl": 600,
            "user_id": "mua-admin",
        }
    ]
    assert "long-term-secret-value" not in response.text


def test_pod_stream_session_requires_stream_settings(authenticated_client):
    _add_pod(authenticated_client)
    configured = authenticated_client.put(
        "/api/v1/settings/runner",
        json={
            "mode": "mobile_use",
            "mobile_use": {
                "access_key_id": "AKLT00000000WXYZ",
                "secret_access_key": "long-term-secret-value",
                "product_id": "prod_123",
            },
        },
    )
    assert configured.status_code == 200

    response = authenticated_client.post("/api/v1/pod-pool/pod_123/stream-session")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stream_settings_incomplete"
    assert response.json()["error"]["details"] == {
        "missing_fields": ["account_id", "sts_role_trn"]
    }


def test_pod_stream_session_rejects_unknown_pod(authenticated_client):
    authenticated_client.app.state.stream_token_gateway = FakeStreamTokenGateway()
    configured = authenticated_client.put(
        "/api/v1/settings/runner",
        json={"mode": "mobile_use", "mobile_use": MOBILE_USE_STREAM_CONFIG},
    )
    assert configured.status_code == 200

    response = authenticated_client.post("/api/v1/pod-pool/missing_pod/stream-session")

    assert response.status_code == 404
