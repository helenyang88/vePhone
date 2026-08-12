from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cua_platform.traces.models import TaskTraceSpan
from cua_platform.traces.schemas import TraceSpanDraft, validate_trace_attributes


class TraceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def insert_allocation_drafts(
        self,
        task_id: str,
        drafts: tuple[TraceSpanDraft, ...],
    ) -> tuple[TaskTraceSpan, ...]:
        safe_attributes = tuple(
            validate_trace_attributes(draft.attributes) for draft in drafts
        )
        next_sequence = (
            self.db.scalar(
                select(func.max(TaskTraceSpan.sequence)).where(
                    TaskTraceSpan.task_id == task_id
                )
            )
            or 0
        ) + 1
        span_ids: dict[str, str] = {}
        inserted: list[TaskTraceSpan] = []
        for offset, (draft, attributes) in enumerate(zip(drafts, safe_attributes)):
            span_id = f"span_{uuid4().hex}"
            parent_span_id = (
                span_ids.get(draft.parent_stable_key)
                if draft.parent_stable_key is not None
                else None
            )
            if draft.parent_stable_key is not None and parent_span_id is None:
                raise ValueError("trace_parent_missing")
            span = TaskTraceSpan(
                id=span_id,
                task_id=task_id,
                stable_key=draft.stable_key,
                parent_span_id=parent_span_id,
                sequence=next_sequence + offset,
                kind=draft.kind,
                name=draft.name,
                status=draft.status,
                started_at=draft.started_at,
                finished_at=draft.finished_at,
                request_id=draft.request_id,
                step_index=draft.step_index,
                error_code=draft.error_code,
                attributes=attributes,
            )
            self.db.add(span)
            span_ids[draft.stable_key] = span_id
            inserted.append(span)
        self.db.flush()
        return tuple(inserted)

    def upsert(
        self,
        task_id: str,
        stable_key: str,
        draft: TraceSpanDraft,
    ) -> TaskTraceSpan:
        attributes = validate_trace_attributes(draft.attributes)
        existing = self.db.scalar(
            select(TaskTraceSpan).where(
                TaskTraceSpan.task_id == task_id,
                TaskTraceSpan.stable_key == stable_key,
            )
        )
        parent_span_id = self._parent_span_id(task_id, draft.parent_stable_key)
        if existing is None:
            next_sequence = (
                self.db.scalar(
                    select(func.max(TaskTraceSpan.sequence)).where(
                        TaskTraceSpan.task_id == task_id
                    )
                )
                or 0
            ) + 1
            existing = TaskTraceSpan(
                id=f"span_{uuid4().hex}",
                task_id=task_id,
                stable_key=stable_key,
                sequence=next_sequence,
            )
            self.db.add(existing)

        existing.parent_span_id = parent_span_id
        existing.kind = draft.kind
        existing.name = draft.name
        existing.status = draft.status
        existing.started_at = draft.started_at
        existing.finished_at = draft.finished_at
        existing.request_id = draft.request_id
        existing.step_index = draft.step_index
        existing.error_code = draft.error_code
        existing.attributes = attributes
        self.db.flush()
        return existing

    def list_for_task(self, task_id: str) -> tuple[TaskTraceSpan, ...]:
        return tuple(
            self.db.scalars(
                select(TaskTraceSpan)
                .where(TaskTraceSpan.task_id == task_id)
                .order_by(TaskTraceSpan.sequence)
            )
        )

    def get_by_stable_key(
        self,
        task_id: str,
        stable_key: str,
    ) -> TaskTraceSpan | None:
        return self.db.scalar(
            select(TaskTraceSpan).where(
                TaskTraceSpan.task_id == task_id,
                TaskTraceSpan.stable_key == stable_key,
            )
        )

    def gateway_call_counts(self, task_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for span in self.list_for_task(task_id):
            action = span.attributes.get("action")
            parts = span.stable_key.rsplit(".", 3)
            if (
                span.kind != "attempt"
                or not isinstance(action, str)
                or len(parts) != 4
                or parts[-2] != "attempt"
            ):
                continue
            try:
                call_number = int(parts[-3])
            except ValueError:
                continue
            counts[action] = max(counts.get(action, 0), call_number)
        return counts

    def _parent_span_id(
        self,
        task_id: str,
        parent_stable_key: str | None,
    ) -> str | None:
        if parent_stable_key is None:
            return None
        parent_id = self.db.scalar(
            select(TaskTraceSpan.id).where(
                TaskTraceSpan.task_id == task_id,
                TaskTraceSpan.stable_key == parent_stable_key,
            )
        )
        if parent_id is None:
            raise ValueError("trace_parent_missing")
        return parent_id
