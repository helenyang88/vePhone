import asyncio
import json
import re
from typing import Protocol

from mua_platform.runners.universal_gateway import UniversalRemoteError, safe_universal_error
from mua_platform.settings.schemas import RunnerConfig

_SESSION_NAME_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


class StreamTokenGateway(Protocol):
    async def assume_role(
        self,
        config: RunnerConfig,
        *,
        pod_id: str,
        user_id: str,
    ) -> dict[str, str]: ...


class VolcengineStreamTokenGateway:
    async def assume_role(
        self,
        config: RunnerConfig,
        *,
        pod_id: str,
        user_id: str,
    ) -> dict[str, str]:
        return await asyncio.to_thread(self._assume_role, config, pod_id, user_id)

    def _assume_role(
        self,
        config: RunnerConfig,
        pod_id: str,
        user_id: str,
    ) -> dict[str, str]:
        if not config.access_key_id or not config.secret_access_key or not config.sts_role_trn:
            raise ValueError("stream_settings_incomplete")
        try:
            import volcenginesdkcore
            import volcenginesdksts

            configuration = volcenginesdkcore.Configuration()
            configuration.ak = config.access_key_id
            configuration.sk = config.secret_access_key
            configuration.region = "cn-north-1"
            configuration.auto_retry = False
            api = volcenginesdksts.STSApi(volcenginesdkcore.ApiClient(configuration))
            response = api.assume_role(
                volcenginesdksts.AssumeRoleRequest(
                    duration_seconds=config.stream_token_ttl_seconds,
                    policy=_stream_policy(config, pod_id, user_id),
                    role_session_name=_role_session_name(user_id),
                    role_trn=config.sts_role_trn,
                )
            )
        except UniversalRemoteError:
            raise
        except Exception as exc:
            raise safe_universal_error(exc) from None

        credentials = getattr(response, "credentials", None)
        token = {
            "AccessKeyID": getattr(credentials, "access_key_id", None),
            "SecretAccessKey": getattr(credentials, "secret_access_key", None),
            "SessionToken": getattr(credentials, "session_token", None),
            "CurrentTime": getattr(credentials, "current_time", None),
            "ExpiredTime": getattr(credentials, "expired_time", None),
        }
        if not all(isinstance(value, str) and value for value in token.values()):
            raise UniversalRemoteError(
                "response_invalid",
                None,
                retryable=False,
                response_received=True,
            )
        return token


def _stream_policy(config: RunnerConfig, pod_id: str, user_id: str) -> str:
    return json.dumps(
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "ACEP:StartScreenShot",
                        "ACEP:MonitorPod",
                        "ACEP:PodStart",
                        "ACEP:BatchPodStart",
                        "ACEP:StartPodEventSync",
                        "ACEP:UpdatePodEventSync",
                        "ACEP:GetMediaToken",
                        "ACEP:ListPod",
                        "ACEP:GetTaskInfo",
                    ],
                    "Resource": [
                        f"trn:ACEP::{config.account_id}:product_id/{config.product_id}",
                        f"trn:ACEP::{config.account_id}:pod_id/{pod_id}",
                        f"trn:ACEP::{config.account_id}:user_id/{user_id}",
                    ],
                }
            ]
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _role_session_name(user_id: str) -> str:
    normalized = _SESSION_NAME_SAFE.sub("-", user_id).strip("-") or "mua-stream"
    return normalized[:64]
