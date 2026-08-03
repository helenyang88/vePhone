import json
from typing import Any

from mua_platform.settings.audit import add_runner_settings_audit
from mua_platform.settings.repository import SettingRepository
from mua_platform.settings.schemas import RunnerConfig, RunnerSettingsUpdate

_FIELDS = (
    "access_key_id",
    "secret_access_key",
    "product_id",
    "account_id",
    "sts_role_trn",
    "stream_token_ttl_seconds",
    "pod_id",
    "ark_api_key",
    "tos_bucket",
    "tos_endpoint",
    "tos_region",
    "use_base64_screenshot",
    "max_step",
    "timeout_seconds",
    "callback_info",
    "output_schema",
    "retry_limit",
    "system_prompt",
    "screen_record",
    "mcp_json",
    "max_output_tokens",
    "gps_info",
)
_REQUIRED_MOBILE_USE_FIELDS = (
    "access_key_id",
    "secret_access_key",
    "product_id",
)


class RunnerSettingsValidationError(ValueError):
    def __init__(self, code: str, details: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


class SettingsService:
    def __init__(self, repository: SettingRepository) -> None:
        self.repository = repository

    def get_runner_config(self) -> RunnerConfig:
        mode = self.repository.get("runner.mode") or "mobile_use"
        values = {
            field: _deserialize_field(field, self.repository.get(f"runner.mobile_use.{field}"))
            for field in _FIELDS
        }
        return RunnerConfig(
            mode=mode,
            **{field: value for field, value in values.items() if value is not None},
        )

    def get_public_settings(self) -> dict[str, Any]:
        config = self.get_runner_config()
        return {
            "mode": config.mode,
            "mobile_use": {
                "access_key_id": _masked_access_key(config.access_key_id),
                "secret_access_key": {"configured": config.secret_access_key is not None},
                "product_id": config.product_id,
                "account_id": config.account_id,
                "sts_role_trn": config.sts_role_trn,
                "stream_token_ttl_seconds": config.stream_token_ttl_seconds,
                "pod_id": config.pod_id,
                "ark_api_key": {"configured": config.ark_api_key is not None},
                "tos_bucket": config.tos_bucket,
                "tos_endpoint": config.tos_endpoint,
                "tos_region": config.tos_region,
                "use_base64_screenshot": config.use_base64_screenshot,
                "max_step": config.max_step,
                "timeout_seconds": config.timeout_seconds,
                "callback_info": config.callback_info,
                "output_schema": config.output_schema,
                "retry_limit": config.retry_limit,
                "system_prompt": config.system_prompt,
                "screen_record": config.screen_record,
                "mcp_json": config.mcp_json,
                "max_output_tokens": config.max_output_tokens,
                "gps_info": config.gps_info,
            },
        }

    def update_runner(
        self,
        payload: RunnerSettingsUpdate,
        actor_user_id: int,
    ) -> dict[str, Any]:
        self.validate_runner(payload)
        changed_values = {
            f"runner.mobile_use.{field}": _serialize_field(
                field,
                getattr(payload.mobile_use, field),
            )
            for field in (
                payload.mobile_use.model_fields_set
                if payload.mobile_use is not None
                else ()
            )
        }
        self.repository.set_many(
            {
                "runner.mode": payload.mode,
                **changed_values,
            }
        )
        changed_fields = [
            key.removeprefix("runner.mobile_use.") for key in changed_values
        ]
        add_runner_settings_audit(
            self.repository.db,
            actor_user_id=actor_user_id,
            mode=payload.mode,
            changed_fields=changed_fields,
        )
        return self.get_public_settings()

    def validate_runner(self, payload: RunnerSettingsUpdate) -> RunnerConfig:
        config = self.get_runner_config()
        merged = config.model_dump(exclude={"mode"})

        if payload.mobile_use is not None:
            for field in payload.mobile_use.model_fields_set:
                value = getattr(payload.mobile_use, field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    raise RunnerSettingsValidationError(
                        "runner_setting_value_invalid",
                        {"field": field},
                    )
                normalized = value.strip() if isinstance(value, str) else value
                merged[field] = normalized

        if payload.mode == "mobile_use":
            missing_fields = [
                field for field in _REQUIRED_MOBILE_USE_FIELDS if not merged[field]
            ]
            if missing_fields:
                raise RunnerSettingsValidationError(
                    "runner_settings_incomplete",
                    {"missing_fields": missing_fields},
                )

        return RunnerConfig(mode=payload.mode, **merged)


def _masked_access_key(value: str | None) -> dict[str, bool | str]:
    if value is None:
        return {"configured": False}
    hint = f"{value[:4]}****{value[-4:]}" if len(value) >= 9 else "configured"
    return {"configured": True, "hint": hint}


def _deserialize_field(field: str, value: str | None) -> Any:
    if value is None:
        return None
    if field in {"use_base64_screenshot", "screen_record"}:
        return value.lower() == "true"
    if field in {
        "max_step",
        "timeout_seconds",
        "retry_limit",
        "max_output_tokens",
        "stream_token_ttl_seconds",
    }:
        return int(value)
    if field == "callback_info":
        return json.loads(value)
    return value


def _serialize_field(field: str, value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if field == "callback_info":
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
