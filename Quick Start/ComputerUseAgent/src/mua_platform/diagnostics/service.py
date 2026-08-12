import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from mua_platform.diagnostics.schemas import (
    PodDiagnostic,
    PodDiagnosticCode,
    ValidationCheck,
    ValidationResult,
)
from mua_platform.runners.base import RunnerAdapter
from mua_platform.settings.schemas import RunnerConfig
from mua_platform.settings.service import SettingsService
from mua_platform.time import Clock

logger = logging.getLogger("mua_platform.diagnostics")

_REQUIRED_COMPUTER_USE_FIELDS = (
    "access_key_id",
    "secret_access_key",
    "account_id",
)


class RunnerSettingsProvider(Protocol):
    def get_runner_config(self) -> RunnerConfig: ...


class RunnerSettingsIncompleteError(ValueError):
    code = "runner_settings_incomplete"

    def __init__(self, missing_fields: list[str]) -> None:
        super().__init__(self.code)
        self.details = {"missing_fields": missing_fields}


class DiagnosticsService:
    def __init__(
        self,
        settings_service: SettingsService | RunnerSettingsProvider,
        runner_factory: Callable[[RunnerConfig], RunnerAdapter],
        clock: Clock,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.settings_service = settings_service
        self.runner_factory = runner_factory
        self.clock = clock
        self.timeout_seconds = timeout_seconds

    async def validate_runner(self) -> ValidationResult:
        config = self._load_config()
        try:
            runner = self.runner_factory(config)
            async with asyncio.timeout(self.timeout_seconds):
                return await runner.validate(config)
        except TimeoutError:
            return ValidationResult(
                runner_mode=config.mode,
                status="failed",
                checks=(
                    ValidationCheck(
                        name="runner_api",
                        status="failed",
                        code="diagnostic_timeout",
                        message="Runner diagnostic timed out",
                        request_id=None,
                    ),
                ),
            )
        except Exception as exc:
            _log_adapter_failure("validate", exc)
            return ValidationResult(
                runner_mode=config.mode,
                status="failed",
                checks=(
                    ValidationCheck(
                        name="runner_api",
                        status="failed",
                        code="diagnostic_internal_error",
                        message="Runner diagnostic failed",
                        request_id=None,
                    ),
                ),
            )

    async def list_pods(self) -> tuple[PodDiagnostic, ...]:
        config = self._load_config()
        try:
            runner = self.runner_factory(config)
            async with asyncio.timeout(self.timeout_seconds):
                return await runner.list_pods(config)
        except TimeoutError:
            return (
                self._unknown_pod(
                    config,
                    "diagnostic_timeout",
                    "Pod diagnostic timed out",
                ),
            )
        except Exception as exc:
            _log_adapter_failure("list_pods", exc)
            return (
                self._unknown_pod(
                    config,
                    "diagnostic_internal_error",
                    "Pod diagnostic failed",
                ),
            )

    def _load_config(self) -> RunnerConfig:
        config = self.settings_service.get_runner_config()
        if config.mode == "mobile_use":
            missing_fields = [
                field for field in _REQUIRED_COMPUTER_USE_FIELDS if not getattr(config, field)
            ]
            if missing_fields:
                raise RunnerSettingsIncompleteError(missing_fields)
        return config

    @staticmethod
    def _unknown_pod(
        config: RunnerConfig,
        code: PodDiagnosticCode,
        message: str,
    ) -> PodDiagnostic:
        return PodDiagnostic(
            pod_id=config.pod_id or "unknown",
            status="unknown",
            product_id=config.product_id or "unknown",
            code=code,
            message=message,
            request_id=None,
        )


def _log_adapter_failure(operation: str, exc: Exception) -> None:
    logger.error(
        "Runner diagnostic adapter failed",
        extra={
            "operation": operation,
            "exception_type": type(exc).__name__,
        },
    )
