from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from cua_platform.db import Base
from cua_platform.runners.base import RunnerEvent
from cua_platform.runners.universal_gateway import GatewayTraceAttempt
from cua_platform.tasks.models import Task
from cua_platform.tasks.repository import SQLiteTaskRepository
from cua_platform.tasks.state_machine import ExecutionStatus, Verdict
from cua_platform.traces.models import TaskTraceSpan
from cua_platform.traces.repository import TraceRepository
from cua_platform.traces.schemas import TraceSpanDraft
from cua_platform.traces.service import TraceService

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture()
def trace_service(db: Session) -> TraceService:
    return TraceService(TraceRepository(db))


def span(
    stable_key: str,
    *,
    parent_stable_key: str | None = None,
    kind: str = "call",
    status: str = "ok",
    request_id: str | None = None,
    attributes: dict | None = None,
    finished_at: datetime | None = NOW + timedelta(milliseconds=25),
) -> TraceSpanDraft:
    return TraceSpanDraft(
        stable_key=stable_key,
        parent_stable_key=parent_stable_key,
        kind=kind,
        name=stable_key,
        status=status,
        started_at=NOW,
        finished_at=finished_at,
        request_id=request_id,
        step_index=None,
        error_code=None,
        attributes=attributes or {},
    )


def test_trace_upsert_is_stable_across_resume(
    db: Session,
    trace_service: TraceService,
):
    draft = span("mobile.result", kind="result", request_id="req-safe")

    first = trace_service.upsert("task-1", "mobile.result", draft)
    second = trace_service.upsert("task-1", "mobile.result", draft)

    assert second.id == first.id
    assert db.scalar(select(func.count(TaskTraceSpan.id))) == 1


def test_trace_upsert_updates_existing_span_without_changing_sequence(
    trace_service: TraceService,
):
    pending = span("mobile.poll.1", status="pending", finished_at=None)
    completed = span(
        "mobile.poll.1",
        status="ok",
        request_id="req-poll",
        attributes={"attempt": 1, "duration_ms": 25},
    )

    first = trace_service.upsert("task-1", "mobile.poll.1", pending)
    updated = trace_service.upsert("task-1", "mobile.poll.1", completed)

    assert (updated.id, updated.sequence) == (first.id, first.sequence)
    assert updated.status == "ok"
    assert updated.request_id == "req-poll"
    assert updated.attributes == {"attempt": 1, "duration_ms": 25}


def test_trace_upsert_resolves_persisted_parent(trace_service: TraceService):
    parent = trace_service.upsert("task-1", "mobile.poll.1", span("mobile.poll.1"))

    child = trace_service.upsert(
        "task-1",
        "mobile.poll.1.attempt.1",
        span(
            "mobile.poll.1.attempt.1",
            parent_stable_key="mobile.poll.1",
            kind="attempt",
        ),
    )

    assert child.parent_span_id == parent.id


def test_trace_repository_recovers_gateway_call_counts(
    db: Session,
    trace_service: TraceService,
):
    for call_number in (1, 2, 3):
        stable_key = f"mobile.step.{call_number}.attempt.1"
        trace_service.upsert(
            "task-1",
            stable_key,
            span(
                stable_key,
                kind="attempt",
                attributes={
                    "action": "ListAgentRunCurrentStep",
                    "method": "GET",
                    "attempt": 1,
                },
            ),
        )

    assert TraceRepository(db).gateway_call_counts("task-1") == {
        "ListAgentRunCurrentStep": 3
    }


def test_gateway_attempts_roll_up_to_final_call_status(
    db: Session,
    trace_service: TraceService,
):
    trace_service.record_gateway_attempt(
        "task-1",
        GatewayTraceAttempt(
            stable_key="mobile.step.1.attempt.1",
            action="ListAgentRunCurrentStep",
            method="GET",
            attempt=1,
            status="error",
            started_at=NOW,
            finished_at=NOW + timedelta(milliseconds=10),
            duration_ms=10,
            request_id="req-retry",
            error_code="remote_unavailable",
        ),
    )
    trace_service.record_gateway_attempt(
        "task-1",
        GatewayTraceAttempt(
            stable_key="mobile.step.1.attempt.2",
            action="ListAgentRunCurrentStep",
            method="GET",
            attempt=2,
            status="ok",
            started_at=NOW + timedelta(milliseconds=250),
            finished_at=NOW + timedelta(milliseconds=270),
            duration_ms=20,
            request_id="req-success",
            error_code=None,
        ),
    )

    spans = TraceRepository(db).list_for_task("task-1")
    assert [(span.stable_key, span.kind, span.status) for span in spans] == [
        ("mobile.step.1", "call", "ok"),
        ("mobile.step.1.attempt.1", "attempt", "error"),
        ("mobile.step.1.attempt.2", "attempt", "ok"),
    ]
    assert spans[0].started_at == NOW
    assert spans[0].finished_at == NOW + timedelta(milliseconds=270)
    assert all(span.parent_span_id == spans[0].id for span in spans[1:])


def test_task_events_persist_trace_synchronously_and_replay_stably(db: Session):
    db.add(
        Task(
            id="task-1",
            case_id="case-1",
            script_version_id="script-1",
            runner_type="mobile_use",
            scenario="success",
            execution_status=ExecutionStatus.RUNNING,
            idempotency_key="idem-1",
            request_fingerprint="{}",
        )
    )
    db.commit()
    repository = SQLiteTaskRepository(db)
    events = (
        RunnerEvent(1, "task_started", {"task_id": "task-1"}),
        RunnerEvent(
            2,
            "step_finished",
            {
                "index": 1,
                "instruction": "open app",
                "status": "passed",
                "assertion_result": "pass",
                "logs": [],
            },
        ),
        RunnerEvent(
            3,
            "task_finished",
            {
                "assertion_results": ["fail"],
                "evidence_complete": True,
                "remote_state": "finished",
                "failure_type": "assertion_failed",
            },
        ),
    )

    repository.record_event("task-1", events[0])
    repository.record_event("task-1", events[1])
    repository.record_event(
        "task-1",
        events[2],
        status=ExecutionStatus.RESULT_READY,
        verdict=Verdict.FAIL,
        failure_type="assertion_failed",
    )
    repository.record_event("task-1", events[1])

    spans = TraceRepository(db).list_for_task("task-1")
    assert [(item.stable_key, item.kind, item.status) for item in spans] == [
        ("event.1", "lifecycle", "ok"),
        ("event.2", "step", "passed"),
        ("event.3", "result", "ok"),
    ]
    assert spans[1].step_index == 1
    assert all(item.attributes == {"runner_type": "mobile_use"} for item in spans)


@pytest.mark.parametrize(
    "attributes",
    [
        {"Prompt": "secret"},
        {"raw_response": "secret"},
        {"action": ["not", "scalar"]},
        {"action": "x" * 257},
        {"attempt": 2**53},
    ],
)
def test_trace_rejects_unsafe_or_unbounded_attributes(
    trace_service: TraceService,
    attributes: dict,
):
    with pytest.raises(ValueError, match="trace_attributes_unsafe"):
        trace_service.upsert(
            "task-1",
            "mobile.start",
            span("mobile.start", attributes=attributes),
        )
