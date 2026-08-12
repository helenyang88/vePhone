import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
from threading import Lock
from typing import Any, Awaitable, Callable, ParamSpec, Protocol, TypeVar
from uuid import uuid4
from weakref import WeakKeyDictionary

from mua_platform.cases.models import TestCase
from mua_platform.pods.gateway import PodGateway
from mua_platform.pods.repository import PodRepository
from mua_platform.pods.schemas import PodDetail, PodPoolSnapshot, VerifiedPodAllocation
from mua_platform.runners.universal_gateway import UniversalRemoteError
from mua_platform.settings.schemas import RunnerConfig
from mua_platform.tasks.models import Task
from mua_platform.tasks.repository import PodLeaseConflict, SQLiteTaskRepository
from mua_platform.time import Clock, SystemClock
from mua_platform.traces.schemas import TraceSpanDraft


logger = logging.getLogger("mua_platform.pod_leases")

P = ParamSpec("P")
R = TypeVar("R")
EXHAUSTION_ERROR_CODES = frozenset({"pod_pool_empty", "pod_pool_exhausted"})

_refresh_locks_guard = Lock()
_refresh_locks_by_loop: WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[str, asyncio.Lock]
] = WeakKeyDictionary()


def _log(level: int, event: str, **fields: object) -> None:
    try:
        logger.log(level, event, extra=fields)
    except Exception:
        # Diagnostics must never change allocation behavior.
        pass


@dataclass
class _AllocationFailureContext:
    allocation_id: str | None = None
    case_id: str | None = None
    product_id: str | None = None
    phase_error_code: str = "allocation_internal_failed"
    error_code: str | None = None
    request_id: str | None = None
    retryable: bool = False

    def fail(self, exc: Exception) -> None:
        if (
            isinstance(exc, PodAllocationError)
            and exc.code in EXHAUSTION_ERROR_CODES
        ):
            return
        error_code = self.error_code
        request_id = self.request_id
        if isinstance(exc, PodAllocationError):
            error_code = error_code or exc.code
            request_id = request_id or exc.request_id
        _log(
            logging.WARNING,
            "pod_allocation_failed",
            allocation_id=self.allocation_id,
            case_id=self.case_id,
            product_id=self.product_id,
            request_id=request_id,
            error_code=error_code or self.phase_error_code,
            retryable=self.retryable,
        )


_allocation_failure_context: ContextVar[_AllocationFailureContext | None] = (
    ContextVar("pod_allocation_failure_context", default=None)
)


def _log_allocation_failure_once(
    function: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        context = _AllocationFailureContext()
        token = _allocation_failure_context.set(context)
        try:
            return await function(*args, **kwargs)
        except Exception as exc:
            if context.allocation_id is not None:
                context.fail(exc)
            raise
        finally:
            _allocation_failure_context.reset(token)

    return wrapped


def _failure_context() -> _AllocationFailureContext:
    context = _allocation_failure_context.get()
    if context is None:
        raise RuntimeError("allocation_failure_context_missing")
    return context


class PodDiscoveryGateway(Protocol):
    async def list_all(self, config: RunnerConfig): ...

    async def detail(self, config: RunnerConfig, pod_id: str) -> PodDetail: ...


class PodDiscoveryError(RuntimeError):
    code = "pod_pool_discovery_failed"

    def __init__(
        self,
        request_id: str | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(self.code)
        self.request_id = request_id
        self.retryable = retryable


class PodAllocationError(RuntimeError):
    def __init__(self, code: str, request_id: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.request_id = request_id


class PodPoolService:
    def __init__(
        self,
        repository: PodRepository,
        gateway: PodDiscoveryGateway | None = None,
        clock: Clock | None = None,
        *,
        config: RunnerConfig | None = None,
    ) -> None:
        self.repository = repository
        self.gateway = gateway or PodGateway()
        self.clock = clock or SystemClock()
        self.config = config

    async def refresh(
        self,
        config: RunnerConfig,
        *,
        before_sync: Callable[[], None] | None = None,
    ) -> PodPoolSnapshot:
        _validate_config(config)
        pool_id = _pool_id(config)
        async with _refresh_lock(pool_id):
            return await self._refresh_serialized(config, before_sync=before_sync)

    async def _refresh_serialized(
        self,
        config: RunnerConfig,
        *,
        before_sync: Callable[[], None] | None,
    ) -> PodPoolSnapshot:
        try:
            page = await self.gateway.list_all(config)
        except UniversalRemoteError as exc:
            self.repository.db.rollback()
            raise PodDiscoveryError(
                exc.request_id,
                retryable=exc.retryable,
            ) from exc
        seen_at = self.clock.now()
        try:
            if before_sync is not None:
                before_sync()
            self.repository.sync(_pool_id(config), page, seen_at=seen_at)
            self.repository.db.commit()
        except Exception:
            self.repository.db.rollback()
            raise
        return self.list_cached(config)

    def list_cached(self, config: RunnerConfig) -> PodPoolSnapshot:
        _validate_config(config)
        return self.repository.list_snapshot(_pool_id(config), now=self.clock.now())

    @_log_allocation_failure_once
    async def allocate_for_case(
        self,
        case: TestCase,
        scenario: str,
        idempotency_key: str,
        runner_type: str,
        *,
        created_by: str = "system",
        runner_config_snapshot: dict[str, Any] | None = None,
    ) -> Task:
        from mua_platform.tasks.models import Task as _Task  # noqa: F401
        config = self._allocation_config()
        pool_id = _pool_id(config)
        task_repository = SQLiteTaskRepository(self.repository.db)
        self.repository.db.rollback()

        preferred_pod_id: str | None = None
        if runner_config_snapshot and isinstance(runner_config_snapshot.get("pod_id"), str):
            preferred_pod_id = runner_config_snapshot["pod_id"]

        allocation_id = uuid4().hex
        failure = _failure_context()
        failure.allocation_id = allocation_id
        failure.case_id = case.id
        failure.product_id = pool_id
        failure.phase_error_code = "allocation_prepare_failed"
        _log(
            logging.INFO,
            "pod_allocation_started",
            allocation_id=allocation_id,
            case_id=case.id,
            product_id=pool_id,
        )
        now = self.clock.now()
        allocation_drafts: list[TraceSpanDraft] = []
        failure.phase_error_code = "allocation_snapshot_failed"
        snapshot = self.repository.list_snapshot(pool_id, now=now)
        cache_age = (
            now - snapshot.refreshed_at
            if snapshot.refreshed_at is not None
            else None
        )
        if cache_age is None or cache_age >= timedelta(seconds=60):
            refresh_started_at = self.clock.now()
            failure.phase_error_code = "allocation_refresh_failed"
            try:
                snapshot = await self.refresh(config)
                refresh_finished_at = self.clock.now()
                request_id = next(
                    (
                        item.request_id
                        for item in snapshot.items
                        if item.request_id is not None
                    ),
                    None,
                )
                allocation_drafts.append(
                    TraceSpanDraft(
                        stable_key="allocation.list",
                        parent_stable_key=None,
                        kind="remote_call",
                        name="ListPod",
                        status="ok",
                        started_at=refresh_started_at,
                        finished_at=refresh_finished_at,
                        request_id=request_id,
                        step_index=None,
                        error_code=None,
                        attributes={
                            "action": "ListPod",
                            "method": "GET",
                            "product_id": pool_id,
                        },
                    )
                )
            except PodDiscoveryError as exc:
                if not exc.retryable or cache_age is None:
                    failure.request_id = exc.request_id
                    failure.retryable = exc.retryable
                    raise PodAllocationError(
                        "pod_pool_discovery_failed",
                        exc.request_id,
                    ) from exc
                if cache_age > timedelta(minutes=5):
                    failure.request_id = exc.request_id
                    failure.retryable = exc.retryable
                    raise PodAllocationError(
                        "pod_pool_stale",
                        exc.request_id,
                    ) from exc
        if not snapshot.active_ids:
            _log(
                logging.WARNING,
                "pod_allocation_exhausted",
                allocation_id=allocation_id,
                case_id=case.id,
                product_id=pool_id,
                candidate_count=0,
            )
            raise PodAllocationError("pod_pool_empty")

        failure.phase_error_code = "allocation_candidates_failed"
        candidates = self.repository.list_allocation_candidates(
            pool_id,
            now=now,
        )
        if preferred_pod_id:
            preferred = [c for c in candidates if c.pod_id == preferred_pod_id]
            if not preferred:
                all_pods = self.repository.get(pool_id, preferred_pod_id)
                if all_pods is None:
                    raise PodAllocationError("pod_not_found")
                raise PodAllocationError("pod_busy")
            candidates = preferred
        candidate_count = len(candidates)
        _log(
            logging.DEBUG,
            "pod_allocation_candidates_loaded",
            allocation_id=allocation_id,
            case_id=case.id,
            product_id=pool_id,
            candidate_count=candidate_count,
        )
        if not candidates:
            _log(
                logging.WARNING,
                "pod_allocation_exhausted",
                allocation_id=allocation_id,
                case_id=case.id,
                product_id=pool_id,
                candidate_count=candidate_count,
            )
            raise PodAllocationError("pod_pool_exhausted" if not preferred_pod_id else "pod_busy")

        for candidate_index, candidate in enumerate(candidates, start=1):
            resource_key = pod_resource_key(
                candidate.product_id,
                candidate.pod_id,
            )
            detail_started_at = self.clock.now()
            failure.phase_error_code = "allocation_detail_failed"
            failure.error_code = None
            failure.request_id = None
            failure.retryable = False
            try:
                detail = await self.gateway.detail(config, candidate.pod_id)
            except UniversalRemoteError as exc:
                self.repository.db.rollback()
                if exc.code in {
                    "credentials_invalid",
                    "permission_denied",
                    "invalid_parameter",
                    "response_invalid",
                }:
                    failure.error_code = exc.code
                    failure.request_id = exc.request_id
                    failure.retryable = exc.retryable
                    raise PodAllocationError(
                        "pod_pool_discovery_failed",
                        exc.request_id,
                    ) from exc
                if exc.retryable:
                    failure.phase_error_code = "allocation_record_failed"
                    current = self.repository.get(
                        pool_id,
                        candidate.pod_id,
                    )
                    if current is not None:
                        self.repository.record_temporary_failure(
                            current,
                            checked_at=self.clock.now(),
                            request_id=exc.request_id,
                        )
                        failure.phase_error_code = "allocation_commit_failed"
                        self.repository.db.commit()
                _log(
                    logging.DEBUG,
                    "pod_allocation_candidate_skipped",
                    allocation_id=allocation_id,
                    case_id=case.id,
                    product_id=candidate.product_id,
                    pod_id=candidate.pod_id,
                    resource_key=resource_key,
                    candidate_index=candidate_index,
                    candidate_count=candidate_count,
                    reason=(
                        "temporary_error"
                        if exc.retryable
                        else "remote_error"
                    ),
                    request_id=exc.request_id,
                    error_code=exc.code,
                    retryable=exc.retryable,
                )
                continue

            checked_at = self.clock.now()
            failure.phase_error_code = "allocation_record_failed"
            self.repository.record_detail(
                candidate,
                checked_at=checked_at,
                online=detail.online,
                remote_status=detail.remote_status,
                request_id=detail.request_id,
            )
            _log(
                logging.DEBUG,
                "pod_allocation_candidate_checked",
                allocation_id=allocation_id,
                case_id=case.id,
                product_id=detail.product_id,
                pod_id=detail.pod_id,
                resource_key=resource_key,
                candidate_index=candidate_index,
                candidate_count=candidate_count,
                request_id=detail.request_id,
            )
            if not detail.online:
                failure.phase_error_code = "allocation_commit_failed"
                self.repository.db.commit()
                _log(
                    logging.DEBUG,
                    "pod_allocation_candidate_skipped",
                    allocation_id=allocation_id,
                    case_id=case.id,
                    product_id=detail.product_id,
                    pod_id=detail.pod_id,
                    resource_key=resource_key,
                    candidate_index=candidate_index,
                    candidate_count=candidate_count,
                    reason="offline",
                    request_id=detail.request_id,
                )
                continue

            allocation = VerifiedPodAllocation(
                product_id=detail.product_id,
                pod_id=detail.pod_id,
                pod_name=detail.pod_name,
                resource_key=pod_resource_key(detail.product_id, detail.pod_id),
                checked_at=checked_at,
                request_id=detail.request_id,
                trace_drafts=(
                    *allocation_drafts,
                    TraceSpanDraft(
                        stable_key=f"allocation.detail:{detail.pod_id}",
                        parent_stable_key=None,
                        kind="remote_call",
                        name="DetailPod",
                        status="ok",
                        started_at=detail_started_at,
                        finished_at=checked_at,
                        request_id=detail.request_id,
                        step_index=None,
                        error_code=None,
                        attributes={
                            "action": "DetailPod",
                            "method": "GET",
                            "pod_id": detail.pod_id,
                            "product_id": detail.product_id,
                        },
                    ),
                ),
            )
            failure.phase_error_code = "allocation_transaction_failed"
            try:
                exec_snapshot = runner_config_snapshot or _base_execution_snapshot(config)
                result = task_repository.create_from_case(
                    case,
                    scenario,
                    idempotency_key=idempotency_key,
                    runner_type=runner_type,
                    created_by=created_by,
                    runner_config_snapshot=exec_snapshot,
                    verified_allocation=allocation,
                )
            except PodLeaseConflict:
                _log(
                    logging.WARNING,
                    "pod_allocation_lease_conflict",
                    allocation_id=allocation_id,
                    case_id=case.id,
                    product_id=detail.product_id,
                    pod_id=detail.pod_id,
                    resource_key=resource_key,
                    candidate_index=candidate_index,
                    candidate_count=candidate_count,
                )
                continue
            except Exception:
                raise
            task = result.task
            if result.disposition == "existing":
                _log(
                    logging.INFO,
                    "pod_allocation_idempotent_hit",
                    allocation_id=allocation_id,
                    task_id=task.id,
                    case_id=case.id,
                )
                return task
            _log(
                logging.INFO,
                "pod_allocation_succeeded",
                allocation_id=allocation_id,
                task_id=task.id,
                case_id=case.id,
                product_id=detail.product_id,
                pod_id=detail.pod_id,
                resource_key=resource_key,
                candidate_index=candidate_index,
                candidate_count=candidate_count,
                request_id=detail.request_id,
            )
            return task

        _log(
            logging.WARNING,
            "pod_allocation_exhausted",
            allocation_id=allocation_id,
            case_id=case.id,
            product_id=pool_id,
            candidate_count=candidate_count,
        )
        raise PodAllocationError("pod_pool_exhausted")

    def _allocation_config(self) -> RunnerConfig:
        if self.config is None:
            raise ValueError("pod_pool_settings_incomplete")
        _validate_config(self.config)
        return self.config


def pod_resource_key(product_id: str, pod_id: str) -> str:
    if not product_id or not pod_id or ":" in product_id:
        raise ValueError("pod_resource_key_invalid")
    return f"{product_id}:{pod_id}"


def _base_execution_snapshot(
    config: RunnerConfig,
) -> dict[str, Any]:
    if not config.account_id:
        raise ValueError("runner_execution_settings_incomplete")
    return {
        key: value
        for key, value in {
        "account_id": config.account_id,
        "tos_bucket": config.tos_bucket,
        "tos_endpoint": config.tos_endpoint,
        "tos_region": config.tos_region,
        "timeout_seconds": config.timeout_seconds,
        "max_step": config.max_step,
        "callback_info": config.callback_info,
        "output_schema": config.output_schema,
        "retry_limit": config.retry_limit,
        "system_prompt": config.system_prompt,
        "mcp_json": config.mcp_json,
        "max_output_tokens": config.max_output_tokens,
        "request_headers": config.request_headers,
        }.items()
        if value is not None
    }


def _validate_config(config: RunnerConfig) -> None:
    if (
        config.mode != "mobile_use"
        or not config.access_key_id
        or not config.secret_access_key
        or not config.account_id
    ):
        raise ValueError("pod_pool_settings_incomplete")


def _pool_id(config: RunnerConfig) -> str:
    if not config.account_id:
        raise ValueError("pod_pool_settings_incomplete")
    return config.account_id


def _refresh_lock(product_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with _refresh_locks_guard:
        locks = _refresh_locks_by_loop.setdefault(loop, {})
        return locks.setdefault(product_id, asyncio.Lock())
