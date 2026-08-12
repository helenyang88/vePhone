import hashlib
import json
from collections.abc import Awaitable, Callable

from cua_platform.cases.models import ScriptVersion
from cua_platform.reusable_scripts.models import ReusableScript
from cua_platform.reusable_scripts.repository import ReusableScriptRepository
from cua_platform.reusable_scripts.schemas import SaveReusableScript
from cua_platform.tasks.models import Task
from cua_platform.tasks.state_machine import ExecutionStatus, Verdict

TaskAllocator = Callable[[ScriptVersion, str, str], Awaitable[Task]]


class ReusableScriptError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ReusableScriptService:
    def __init__(
        self,
        repository: ReusableScriptRepository,
        allocator: TaskAllocator | None = None,
    ):
        self.repository = repository
        self.allocator = allocator

    def save(
        self,
        task_id: str,
        request: SaveReusableScript,
        actor_id: str,
    ) -> ReusableScript:
        if not actor_id:
            raise ReusableScriptError("actor_required")
        task = self.repository.get_task(task_id)
        if task is None:
            raise ReusableScriptError("task_not_found")
        if not _is_saveable(task):
            raise ReusableScriptError("script_not_saveable")
        case = self.repository.get_case(task.case_id)
        if case is None or self.repository.get_version(task.script_version_id) is None:
            raise ReusableScriptError("script_source_not_found")
        request_fingerprint = _canonical_save_fingerprint(request)
        try:
            return self.repository.save(
                task=task,
                case=case,
                name=request.name,
                description=request.description,
                idempotency_key=request.idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        except ValueError as exc:
            if str(exc) == "idempotency_conflict":
                raise ReusableScriptError("idempotency_conflict") from exc
            raise

    def list(self) -> list[ReusableScript]:
        return self.repository.list()

    def get(self, script_id: str) -> ReusableScript:
        reusable = self.repository.get(script_id)
        if reusable is None:
            raise ReusableScriptError("reusable_script_not_found")
        return reusable

    def archive(self, script_id: str) -> ReusableScript:
        return self._transition(script_id, expected="active", target="archived")

    def restore(self, script_id: str) -> ReusableScript:
        return self._transition(script_id, expected="archived", target="active")

    async def execute(
        self,
        script_id: str,
        version_id: str,
        idempotency_key: str,
    ) -> Task:
        reusable = self.get(script_id)
        if reusable.status != "active":
            raise ReusableScriptError("script_archived")
        if version_id not in {
            reusable.source_script_version_id,
            reusable.current_version_id,
        }:
            raise ReusableScriptError("script_version_not_found")
        version = self.repository.get_version(version_id)
        if version is None:
            raise ReusableScriptError("script_version_not_found")
        if self.allocator is None:
            raise RuntimeError("task_allocator_not_configured")
        execution_key = _execution_idempotency_key(reusable.id, idempotency_key)
        return await self.allocator(version, execution_key, reusable.id)

    def _transition(
        self,
        script_id: str,
        *,
        expected: str,
        target: str,
    ) -> ReusableScript:
        existing = self.get(script_id)
        if existing.status == target:
            return existing
        changed = self.repository.transition_status(
            script_id,
            expected=expected,
            target=target,
        )
        if changed is None:
            raise ReusableScriptError("script_status_conflict")
        return changed


def _is_saveable(task: Task) -> bool:
    return (
        task.execution_status == ExecutionStatus.RESULT_READY
        and task.verdict in {Verdict.PASS, Verdict.FAIL}
    )


def _canonical_save_fingerprint(request: SaveReusableScript) -> str:
    return json.dumps(
        {
            "description": request.description,
            "name": request.name,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _execution_idempotency_key(script_id: str, client_key: str) -> str:
    digest = hashlib.sha256(f"{script_id}\0{client_key}".encode()).hexdigest()
    return f"reusable:{digest}"
