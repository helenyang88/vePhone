from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from mua_platform.settings.schemas import AgentRuntimeOptions


class TestCaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    module: str | None = Field(default=None, max_length=100)
    content_markdown: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    automation_level: str = Field(default="manual_confirm", max_length=32)
    default_agent_options: AgentRuntimeOptions | None = None


class TestCaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    module: str | None = Field(default=None, max_length=100)
    content_markdown: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    automation_level: str | None = Field(default=None, max_length=32)
    default_agent_options: AgentRuntimeOptions | None = None


class TestCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    module: str | None
    content_markdown: str
    tags: list[str]
    automation_level: str
    default_agent_options: AgentRuntimeOptions | None
    execution_count: int
    pass_count: int
    fail_count: int
    last_executed_at: datetime | None
    bound_plan_count: int = 0
    created_by: str
    created_at: datetime
    updated_at: datetime


class TestCaseListResponse(BaseModel):
    items: list[TestCaseResponse]
    total: int
    page: int
    page_size: int


class CaseStatsResponse(BaseModel):
    total: int
    auto_count: int
    today_executions: int
    total_executions: int
    pass_rate: int


class CaseExecuteRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=255)
    pod_id: str | None = Field(default=None, max_length=128)
    timeout_seconds: int | None = Field(default=None, ge=1, le=86400)
    agent_config_mode: str = Field(
        default="global",
        pattern="^(global|custom|case_default)$",
    )
    agent_options: AgentRuntimeOptions | None = None


class CaseBatchDeleteRequest(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=100)


class CaseBatchDeleteItem(BaseModel):
    case_id: str
    status: str
    code: str | None = None
    message: str | None = None


class CaseBatchDeleteResponse(BaseModel):
    deleted_count: int
    failed_count: int
    items: list[CaseBatchDeleteItem]


class CaseBoundTestPlanItem(BaseModel):
    id: str
    name: str
    test_type: str
    case_count: int
    has_active_execution: bool
    created_by: str
    updated_at: datetime


class CaseBoundTestPlanListResponse(BaseModel):
    items: list[CaseBoundTestPlanItem]
    total: int
    page: int
    page_size: int


class CaseImportPreviewRequest(BaseModel):
    format: str = Field(pattern="^(csv|markdown|excel)$")
    content: str = Field(min_length=1)


class CaseImportPreviewItem(BaseModel):
    row: int
    status: str
    messages: list[str] = Field(default_factory=list)
    draft: TestCaseCreate


class CaseImportSummary(BaseModel):
    total: int
    valid: int
    warning: int
    error: int


class CaseImportPreviewResponse(BaseModel):
    items: list[CaseImportPreviewItem]
    summary: CaseImportSummary


class CaseImportConfirmRequest(BaseModel):
    items: list[TestCaseCreate] = Field(min_length=1, max_length=100)


class CaseImportConfirmResponse(BaseModel):
    created_count: int
    items: list[TestCaseResponse]


class TagListResponse(BaseModel):
    items: list[str]


class ModuleListResponse(BaseModel):
    items: list[str]


class CreatorListResponse(BaseModel):
    items: list[str]
