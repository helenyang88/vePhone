import json
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cua_platform.cases.models import ScriptVersion, TestCase
from cua_platform.reusable_scripts.models import ReusableScript, utc_now
from cua_platform.tasks.models import Task


class ReusableScriptRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_task(self, task_id: str) -> Task | None:
        return self.db.get(Task, task_id)

    def get_case(self, case_id: str) -> TestCase | None:
        return self.db.get(TestCase, case_id)

    def get_version(self, version_id: str) -> ScriptVersion | None:
        return self.db.get(ScriptVersion, version_id)

    def get(self, script_id: str) -> ReusableScript | None:
        return self.db.get(ReusableScript, script_id)

    def list(self) -> list[ReusableScript]:
        return list(
            self.db.scalars(
                select(ReusableScript).order_by(ReusableScript.created_at.desc())
            )
        )

    def save(
        self,
        *,
        task: Task,
        case: TestCase,
        name: str,
        description: str | None,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> ReusableScript:
        reusable = ReusableScript(
            id=f"rscript_{uuid4().hex}",
            name=name,
            description=description,
            source_task_id=task.id,
            source_script_version_id=task.script_version_id,
            current_version_id=task.script_version_id,
            app_name=case.app_name,
            app_package=None,
            status="active",
            idempotency_key=idempotency_key,
        )
        try:
            self.db.add(reusable)
            self.db.commit()
            return reusable
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(ReusableScript).where(
                    ReusableScript.source_task_id == task.id,
                    ReusableScript.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            if _stored_request_fingerprint(existing) != request_fingerprint:
                raise ValueError("idempotency_conflict")
            return existing

    def transition_status(
        self,
        script_id: str,
        *,
        expected: str,
        target: str,
    ) -> ReusableScript | None:
        changed = self.db.execute(
            update(ReusableScript)
            .where(
                ReusableScript.id == script_id,
                ReusableScript.status == expected,
            )
            .values(status=target, updated_at=utc_now())
        )
        if changed.rowcount != 1:
            self.db.rollback()
            return None
        self.db.commit()
        return self.get(script_id)


def _stored_request_fingerprint(script: ReusableScript) -> str:
    return json.dumps(
        {
            "description": script.description,
            "name": script.name,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
