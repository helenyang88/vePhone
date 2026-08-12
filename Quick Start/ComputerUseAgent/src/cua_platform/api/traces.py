from typing import Literal

from fastapi import APIRouter, Query

from cua_platform.api.deps import CurrentUser, Database
from cua_platform.api.errors import api_error
from cua_platform.traces.repository import TraceRepository
from cua_platform.traces.service import TraceService

router = APIRouter(prefix="/api/v1")


@router.get("/tasks/{task_id}/trace")
def get_task_trace(
    task_id: str,
    db: Database,
    _user: CurrentUser,
    view: Literal["tree", "flat"] = Query(default="tree"),
    include_attempts: Literal["true", "false"] = Query(default="true"),
) -> dict:
    try:
        response = TraceService(TraceRepository(db)).get(
            task_id,
            view,
            include_attempts == "true",
        )
    except ValueError as exc:
        if str(exc).startswith("task_not_found:"):
            raise api_error(404, "task_not_found", "Task not found") from exc
        raise
    exclude = {"spans": {"__all__": {"children"}}} if view == "flat" else None
    return response.model_dump(mode="json", exclude=exclude)
