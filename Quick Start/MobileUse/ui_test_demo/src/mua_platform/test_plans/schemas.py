from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from mua_platform.cases.schemas import TestCaseResponse
from mua_platform.tasks.schemas import TaskExecutionConfig

TestType = Literal["new_feature", "regression"]


class TestPlanWrite(BaseModel):
    name: str
    description: str | None = Field(default=None, max_length=2000)
    test_type: TestType = "regression"
    tags: list[str] = Field(default_factory=list)
    case_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("test_plan_name_required")
        if len(normalized) > 100:
            raise ValueError("test_plan_name_too_long")
        try:
            normalized.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("test_plan_name_invalid_unicode") from exc
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            tag = value.strip()
            if not tag or len(tag) > 32:
                raise ValueError("test_plan_tag_length")
            try:
                tag.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("test_plan_tag_invalid_unicode") from exc
            if tag not in seen:
                seen.add(tag)
                normalized.append(tag)
        return normalized

    @field_validator("case_ids")
    @classmethod
    def require_unique_case_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("test_plan_case_ids_must_be_unique")
        return values


class TagResponse(BaseModel):
    name: str
    foreground_color: str
    background_color: str
    case_count: int | None = None


class LatestPlanExecutionResponse(BaseModel):
    execution_id: str
    task_batch_id: str
    report_status: str
    pass_rate: float
    created_at: datetime


class TestPlanResponse(BaseModel):
    id: str
    name: str
    description: str | None
    test_type: TestType
    tags: list[TagResponse]
    case_ids: list[str]
    case_count: int
    execution_count: int
    latest_execution: LatestPlanExecutionResponse | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class TestPlanListResponse(BaseModel):
    items: list[TestPlanResponse]
    total: int
    page: int
    page_size: int


class TestPlanStatsResponse(BaseModel):
    active_plan_count: int
    distinct_case_count: int
    execution_count: int
    latest_completed_pass_rate: float


class TagListResponse(BaseModel):
    items: list[TagResponse]
    total: int
    page: int
    page_size: int


class TestPlanCaseListResponse(BaseModel):
    items: list[TestCaseResponse]
    total: int
    page: int
    page_size: int


ReportStatus = Literal[
    "queued",
    "running",
    "success",
    "failure",
    "exception",
    "cancelled",
]


class PlanReportSummary(BaseModel):
    execution_id: str
    task_batch_id: str
    test_plan_id: str | None
    plan_name_snapshot: str
    report_status: ReportStatus
    pass_rate: float
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: int | None


class PlanReportStats(BaseModel):
    report_count: int
    success_count: int
    failure_count: int
    average_pass_rate: float


ReportTaskExecutionStatus = Literal[
    "script_pending",
    "queued",
    "running",
    "result_ready",
    "cancelled",
    "unknown",
]
ReportTaskVerdict = Literal["pass", "fail", "unknown"]


class PlanReportTask(BaseModel):
    task_id: str
    case_id: str
    case_title: str
    case_deleted: bool = False
    execution_status: ReportTaskExecutionStatus
    verdict: ReportTaskVerdict | None
    failure_type: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: int | None


class PlanReportDetail(PlanReportSummary):
    plan_tags_snapshot: list[str]
    case_ids_snapshot: list[str]
    device_strategy_snapshot: str
    pod_ids_snapshot: list[str]
    concurrency_snapshot: int
    runner_type_snapshot: str
    config_snapshot: TaskExecutionConfig
    pass_count: int
    fail_count: int
    exception_count: int
    cancelled_count: int
    queued_count: int
    running_count: int
    tasks: list[PlanReportTask]
    tasks_total: int
    page: int
    page_size: int


class PlanReportListResponse(BaseModel):
    items: list[PlanReportSummary]
    total: int
    page: int
    page_size: int
