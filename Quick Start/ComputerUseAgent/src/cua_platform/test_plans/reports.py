from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, String, case, cast, func, select
from sqlalchemy.orm import Session

from cua_platform.business.models import DEFAULT_BUSINESS_ID
from cua_platform.cases.models import TestCase
from cua_platform.tasks.execution_config import public_execution_config
from cua_platform.tasks.models import Task, TaskBatch
from cua_platform.tasks.schemas import TaskExecutionConfig
from cua_platform.tasks.state_machine import ExecutionStatus, Verdict
from cua_platform.test_plans.models import PlanExecution
from cua_platform.test_plans.schemas import (
    PlanReportDetail,
    PlanReportStats,
    PlanReportSummary,
    PlanReportTask,
    ReportStatus,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def report_status(
    batch_status: str,
    batch_verdict: str | None,
    failure_types: set[str],
) -> ReportStatus:
    if batch_status == ExecutionStatus.QUEUED.value:
        return "queued"
    if batch_status == ExecutionStatus.RUNNING.value:
        return "running"
    if batch_status == ExecutionStatus.CANCELLED.value:
        return "cancelled"
    if (
        batch_status == ExecutionStatus.RESULT_READY.value
        and batch_verdict == Verdict.PASS.value
    ):
        return "success"
    if failure_types - {"assertion_failed"}:
        return "exception"
    if (
        batch_status == ExecutionStatus.RESULT_READY.value
        and batch_verdict == Verdict.FAIL.value
    ):
        return "failure"
    return "exception"


def pass_rate(pass_count: int, snapshot_total: int) -> float:
    if not snapshot_total:
        return 0.0
    return round(pass_count / snapshot_total * 100, 2)


class PlanReportService:
    def __init__(self, db: Session):
        self.db = db

    def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        test_plan_id: str | None,
        status: ReportStatus | None,
        created_after: datetime | None,
        search: str | None = None,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> tuple[list[PlanReportSummary], int]:
        aggregate = _task_aggregate()
        status_column = _report_status_expression(aggregate).label(
            "report_status"
        )
        filters = _filters(
            status_column=status_column,
            test_plan_id=test_plan_id,
            status=status,
            created_after=created_after,
            search=search,
            business_id=business_id,
        )
        total = self.db.scalar(
            select(func.count(PlanExecution.id))
            .join(
                TaskBatch,
                TaskBatch.id == PlanExecution.task_batch_id,
            )
            .outerjoin(
                aggregate,
                aggregate.c.batch_id == TaskBatch.id,
            )
            .where(*filters)
        ) or 0
        rows = self.db.execute(
            _summary_query(aggregate, status_column)
            .where(*filters)
            .order_by(
                PlanExecution.created_at.desc(),
                PlanExecution.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        now = utc_now()
        return [
            _summary_from_row(row, now=now)
            for row in rows
        ], total

    def stats(
        self,
        *,
        test_plan_id: str | None,
        status: ReportStatus | None,
        created_after: datetime | None,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> PlanReportStats:
        aggregate = _task_aggregate()
        status_column = _report_status_expression(aggregate).label(
            "report_status"
        )
        filters = _filters(
            status_column=status_column,
            test_plan_id=test_plan_id,
            status=status,
            created_after=created_after,
            business_id=business_id,
        )
        snapshot_total = func.json_array_length(
            PlanExecution.case_ids_snapshot
        )
        pass_rate_column = case(
            (
                snapshot_total > 0,
                func.coalesce(aggregate.c.pass_count, 0)
                * 100.0
                / snapshot_total,
            ),
            else_=0.0,
        )
        row = self.db.execute(
            select(
                func.count(PlanExecution.id).label("report_count"),
                func.count(PlanExecution.id)
                .filter(status_column == "success")
                .label("success_count"),
                func.count(PlanExecution.id)
                .filter(status_column == "failure")
                .label("failure_count"),
                func.coalesce(
                    func.avg(pass_rate_column),
                    0.0,
                ).label("average_pass_rate"),
            )
            .join(
                TaskBatch,
                TaskBatch.id == PlanExecution.task_batch_id,
            )
            .outerjoin(
                aggregate,
                aggregate.c.batch_id == TaskBatch.id,
            )
            .where(*filters)
        ).one()
        return PlanReportStats(
            report_count=row.report_count or 0,
            success_count=row.success_count or 0,
            failure_count=row.failure_count or 0,
            average_pass_rate=round(row.average_pass_rate or 0.0, 2),
        )

    def get_detail(
        self,
        execution_id: str,
        *,
        page: int,
        page_size: int,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> PlanReportDetail | None:
        aggregate = _task_aggregate()
        status_column = _report_status_expression(aggregate).label(
            "report_status"
        )
        row = self.db.execute(
            _summary_query(aggregate, status_column).where(
                PlanExecution.id == execution_id,
                PlanExecution.business_id == business_id,
            )
        ).one_or_none()
        if row is None:
            return None

        now = utc_now()
        summary = _summary_from_row(row, now=now)
        tasks_total = self.db.scalar(
            select(func.count(Task.id)).where(
                Task.batch_id == row.task_batch_id
            )
        ) or 0
        task_rows = self.db.execute(
            select(
                Task.id.label("task_id"),
                Task.case_id.label("case_id"),
                TestCase.title.label("case_title"),
                TestCase.deleted_at.label("case_deleted_at"),
                cast(Task.execution_status, String).label(
                    "execution_status"
                ),
                cast(Task.verdict, String).label("verdict"),
                Task.failure_type.label("failure_type"),
                Task.created_at.label("created_at"),
                Task.started_at.label("started_at"),
                Task.finished_at.label("finished_at"),
            )
            .join(TestCase, TestCase.id == Task.case_id)
            .where(Task.batch_id == row.task_batch_id)
            .order_by(Task.batch_position, Task.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        tasks = [
            PlanReportTask(
                task_id=task_row.task_id,
                case_id=task_row.case_id,
                case_title=task_row.case_title,
                case_deleted=task_row.case_deleted_at is not None,
                execution_status=_controlled_task_status(
                    task_row.execution_status
                ),
                verdict=_controlled_task_verdict(task_row.verdict),
                failure_type=task_row.failure_type,
                created_at=_as_utc(task_row.created_at),
                started_at=_as_utc(task_row.started_at),
                finished_at=_as_utc(task_row.finished_at),
                duration_seconds=_duration_seconds(
                    task_row.started_at,
                    task_row.finished_at,
                    _controlled_task_status(task_row.execution_status),
                    now=now,
                ),
            )
            for task_row in task_rows
        ]
        return PlanReportDetail(
            **summary.model_dump(),
            plan_tags_snapshot=list(row.plan_tags_snapshot),
            case_ids_snapshot=list(row.case_ids_snapshot),
            device_strategy_snapshot=row.device_strategy_snapshot,
            pod_ids_snapshot=list(row.pod_ids_snapshot),
            concurrency_snapshot=row.concurrency_snapshot,
            runner_type_snapshot=row.runner_type_snapshot,
            config_snapshot=TaskExecutionConfig.model_validate(
                public_execution_config(row.config_snapshot)
            ),
            pass_count=row.pass_count,
            fail_count=row.fail_count,
            exception_count=row.exception_count,
            cancelled_count=row.cancelled_count,
            queued_count=row.queued_count,
            running_count=row.running_count,
            tasks=tasks,
            tasks_total=tasks_total,
            page=page,
            page_size=page_size,
        )

    def list_plan_executions(
        self,
        plan_id: str,
        *,
        page: int,
        page_size: int,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> tuple[list[PlanReportSummary], int]:
        return self.list_paginated(
            page=page,
            page_size=page_size,
            test_plan_id=plan_id,
            status=None,
            created_after=None,
            business_id=business_id,
        )


def _task_aggregate():
    return (
        select(
            Task.batch_id.label("batch_id"),
            func.count(Task.id)
            .filter(
                Task.execution_status == ExecutionStatus.RESULT_READY,
                Task.verdict == Verdict.PASS,
            )
            .label("pass_count"),
            func.count(Task.id)
            .filter(
                Task.execution_status == ExecutionStatus.RESULT_READY,
                Task.verdict == Verdict.FAIL,
                (
                    Task.failure_type.is_(None)
                    | (Task.failure_type == "assertion_failed")
                ),
            )
            .label("fail_count"),
            func.count(Task.id)
            .filter(
                Task.execution_status == ExecutionStatus.RESULT_READY,
                Task.verdict == Verdict.FAIL,
                Task.failure_type.is_not(None),
                Task.failure_type != "assertion_failed",
            )
            .label("exception_count"),
            func.count(Task.id)
            .filter(Task.execution_status == ExecutionStatus.CANCELLED)
            .label("cancelled_count"),
            func.count(Task.id)
            .filter(Task.execution_status == ExecutionStatus.QUEUED)
            .label("queued_count"),
            func.count(Task.id)
            .filter(Task.execution_status == ExecutionStatus.RUNNING)
            .label("running_count"),
        )
        .where(Task.batch_id.is_not(None))
        .group_by(Task.batch_id)
        .subquery()
    )


def _report_status_expression(aggregate):
    exceptional = func.coalesce(aggregate.c.exception_count, 0)
    batch_status = cast(TaskBatch.execution_status, String)
    batch_verdict = cast(TaskBatch.verdict, String)
    return case(
        (
            batch_status == ExecutionStatus.QUEUED.value,
            "queued",
        ),
        (
            batch_status == ExecutionStatus.RUNNING.value,
            "running",
        ),
        (
            batch_status == ExecutionStatus.CANCELLED.value,
            "cancelled",
        ),
        (
            (
                batch_status == ExecutionStatus.RESULT_READY.value
            )
            & (batch_verdict == Verdict.PASS.value),
            "success",
        ),
        (exceptional > 0, "exception"),
        (
            (
                batch_status == ExecutionStatus.RESULT_READY.value
            )
            & (batch_verdict == Verdict.FAIL.value),
            "failure",
        ),
        else_="exception",
    )


def _filters(
    *,
    status_column,
    test_plan_id: str | None,
    status: ReportStatus | None,
    created_after: datetime | None,
    search: str | None = None,
    business_id: str = DEFAULT_BUSINESS_ID,
) -> list:
    filters = [PlanExecution.business_id == business_id]
    if test_plan_id is not None:
        filters.append(PlanExecution.test_plan_id == test_plan_id)
    if status is not None:
        filters.append(status_column == status)
    if created_after is not None:
        filters.append(PlanExecution.created_at >= created_after)
    if search and search.strip():
        filters.append(TaskBatch.id.ilike(f"%{search.strip()}%"))
    return filters


def _summary_query(aggregate, status_column) -> Select:
    return (
        select(
            PlanExecution.id.label("execution_id"),
            PlanExecution.task_batch_id.label("task_batch_id"),
            PlanExecution.test_plan_id.label("test_plan_id"),
            PlanExecution.plan_name_snapshot.label("plan_name_snapshot"),
            PlanExecution.plan_tags_snapshot.label("plan_tags_snapshot"),
            PlanExecution.case_ids_snapshot.label("case_ids_snapshot"),
            PlanExecution.device_strategy_snapshot.label(
                "device_strategy_snapshot"
            ),
            PlanExecution.pod_ids_snapshot.label("pod_ids_snapshot"),
            PlanExecution.concurrency_snapshot.label(
                "concurrency_snapshot"
            ),
            PlanExecution.runner_type_snapshot.label(
                "runner_type_snapshot"
            ),
            PlanExecution.config_snapshot.label("config_snapshot"),
            PlanExecution.created_at.label("created_at"),
            TaskBatch.started_at.label("started_at"),
            TaskBatch.finished_at.label("finished_at"),
            cast(TaskBatch.execution_status, String).label("batch_status"),
            cast(TaskBatch.verdict, String).label("batch_verdict"),
            status_column,
            func.coalesce(aggregate.c.pass_count, 0).label("pass_count"),
            func.coalesce(aggregate.c.fail_count, 0).label("fail_count"),
            func.coalesce(
                aggregate.c.exception_count,
                0,
            ).label("exception_count"),
            func.coalesce(
                aggregate.c.cancelled_count,
                0,
            ).label("cancelled_count"),
            func.coalesce(
                aggregate.c.queued_count,
                0,
            ).label("queued_count"),
            func.coalesce(
                aggregate.c.running_count,
                0,
            ).label("running_count"),
        )
        .join(
            TaskBatch,
            TaskBatch.id == PlanExecution.task_batch_id,
        )
        .outerjoin(
            aggregate,
            aggregate.c.batch_id == TaskBatch.id,
        )
    )


def _summary_from_row(row, *, now: datetime) -> PlanReportSummary:
    failure_types = (
        {"exception"}
        if row.exception_count
        else {"assertion_failed"} if row.fail_count else set()
    )
    return PlanReportSummary(
        execution_id=row.execution_id,
        task_batch_id=row.task_batch_id,
        test_plan_id=row.test_plan_id,
        plan_name_snapshot=row.plan_name_snapshot,
        report_status=report_status(
            row.batch_status,
            row.batch_verdict,
            failure_types,
        ),
        pass_rate=pass_rate(
            row.pass_count,
            len(row.case_ids_snapshot),
        ),
        created_at=_as_utc(row.created_at),
        started_at=_as_utc(row.started_at),
        finished_at=_as_utc(row.finished_at),
        duration_seconds=_duration_seconds(
            row.started_at,
            row.finished_at,
            row.batch_status,
            now=now,
        ),
    )


def _duration_seconds(
    started_at: datetime | None,
    finished_at: datetime | None,
    execution_status: str,
    *,
    now: datetime,
) -> int | None:
    if started_at is None:
        return None
    started = _as_utc(started_at)
    if (
        execution_status == ExecutionStatus.RUNNING.value
        and finished_at is None
    ):
        end = now
    elif finished_at is not None:
        end = _as_utc(finished_at)
    else:
        return None
    return max(0, int((end - started).total_seconds()))


def _controlled_task_status(value: str) -> str:
    if value in {status.value for status in ExecutionStatus}:
        return value
    return "unknown"


def _controlled_task_verdict(value: str | None) -> str | None:
    if value is None or value in {verdict.value for verdict in Verdict}:
        return value
    return "unknown"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
