from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SaveReusableScript(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=255)


class ExecuteReusableScript(BaseModel):
    version_id: str = Field(min_length=1, max_length=40)
    idempotency_key: str = Field(min_length=1, max_length=255)


class ReusableScriptVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    steps: list[dict]


class ReusableScriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    source_task_id: str
    source_script_version_id: str
    current_version_id: str
    app_name: str
    app_package: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    script_version: ReusableScriptVersionResponse


class ReusableScriptListResponse(BaseModel):
    items: list[ReusableScriptResponse]
