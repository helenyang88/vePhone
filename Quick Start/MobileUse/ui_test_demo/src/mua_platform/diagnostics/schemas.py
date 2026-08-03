from dataclasses import dataclass
from typing import Literal

from mua_platform.settings.schemas import RunnerMode

ValidationCheckName = Literal["credentials", "runner_api", "pod"]
ValidationStatus = Literal["passed", "failed"]
PodStatus = Literal["available", "busy", "offline", "unknown"]
PodDiagnosticCode = Literal[
    "pod_available",
    "pod_not_found",
    "pod_unavailable",
    "credentials_invalid",
    "permission_denied",
    "runner_api_unreachable",
    "runner_api_unavailable",
    "request_rejected",
    "diagnostic_timeout",
    "diagnostic_internal_error",
]


@dataclass(frozen=True)
class ValidationCheck:
    name: ValidationCheckName
    status: ValidationStatus
    code: str
    message: str
    request_id: str | None


@dataclass(frozen=True)
class ValidationResult:
    runner_mode: RunnerMode
    status: ValidationStatus
    checks: tuple[ValidationCheck, ...]


@dataclass(frozen=True)
class PodDiagnostic:
    pod_id: str
    status: PodStatus
    product_id: str
    code: PodDiagnosticCode
    message: str
    request_id: str | None
