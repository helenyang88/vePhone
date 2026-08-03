from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from mua_platform.cases.models import TestCase as CaseModel
from mua_platform.db import Base
from mua_platform.pods.models import DiscoveredPod
from mua_platform.tasks.models import PodLease, Task, TaskBatch, TaskRunnerConfig
from mua_platform.tasks.repository import SQLiteTaskRepository
from mua_platform.tasks.scheduler import BatchScheduler
from mua_platform.tasks.state_machine import ExecutionStatus, Verdict


def _seed_batch(
    db: Session,
    *,
    strategy: str,
    pod_ids: list[str],
    concurrency: int,
    task_count: int = 3,
) -> TaskBatch:
    batch = TaskBatch(
        id=f"batch_{strategy}",
        name="调度测试",
        test_type="regression",
        selection_mode="multi_cases",
        selection_snapshot={},
        device_strategy=strategy,
        pod_ids=pod_ids,
        concurrency=concurrency,
        device_wait_timeout_seconds=300,
        runner_type="mobile_use",
        config_snapshot={"product_id": "product-1"},
        execution_status=ExecutionStatus.QUEUED,
        idempotency_key=f"key-{strategy}",
        request_fingerprint="{}",
        created_by="admin",
    )
    for index in range(task_count):
        case = CaseModel(
            id=f"case_{strategy}_{index}",
            title=f"用例 {index}",
            module="调度",
            content_markdown="- 执行",
            tags=[],
            automation_level="auto",
            created_by="admin",
        )
        task = Task(
            id=f"task_{strategy}_{index}",
            case_id=case.id,
            batch_id=batch.id,
            batch_position=index,
            queue_reason="waiting_for_any_device",
            runner_type="mobile_use",
            scenario=case.title,
            created_by="admin",
            execution_status=ExecutionStatus.QUEUED,
            idempotency_key=f"task-key-{strategy}-{index}",
            request_fingerprint="{}",
            version=1,
        )
        task.runner_config = TaskRunnerConfig(
            config_snapshot={"product_id": "product-1"}
        )
        db.add(case)
        batch.tasks.append(task)
    db.add(batch)
    db.commit()
    return batch


def _seed_pod(
    db: Session,
    pod_id: str,
    now: datetime,
    *,
    status: int = 1,
    discovery_state: str = "active",
) -> DiscoveredPod:
    pod = DiscoveredPod(
        id=f"row_{pod_id}",
        product_id="product-1",
        pod_id=pod_id,
        pod_name=pod_id,
        pod_status_code=status,
        discovery_state=discovery_state,
        last_seen_at=now,
    )
    db.add(pod)
    db.commit()
    return pod


def test_automatic_scheduler_reserves_only_batch_concurrency():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            batch = _seed_batch(
                db,
                strategy="automatic",
                pod_ids=[],
                concurrency=2,
            )
            _seed_pod(db, "pod-a", now)
            _seed_pod(db, "pod-b", now)
            _seed_pod(db, "pod-c", now)

            assigned = BatchScheduler(db).schedule(now)

            assert len(assigned) == 2
            leases = list(db.scalars(select(PodLease)))
            assert len(leases) == 2
            assert {lease.task_id for lease in leases} == set(assigned)
            remaining = next(task for task in batch.tasks if task.id not in assigned)
            assert remaining.queue_reason == "waiting_for_capacity"
    finally:
        engine.dispose()


def test_released_capacity_assigns_next_batch_child():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            batch = _seed_batch(
                db,
                strategy="automatic",
                pod_ids=[],
                concurrency=2,
            )
            _seed_pod(db, "pod-a", now)
            _seed_pod(db, "pod-b", now)

            first_wave = BatchScheduler(db).schedule(now)
            assert len(first_wave) == 2
            completed_id = first_wave[0]
            repository = SQLiteTaskRepository(db)
            repository.finish(
                completed_id,
                ExecutionStatus.RESULT_READY,
                Verdict.PASS,
                None,
            )
            assert repository.release_lease(
                completed_id,
                reason="terminal",
            )

            second_wave = BatchScheduler(db).schedule(
                now + timedelta(seconds=1)
            )

            remaining_id = next(
                task.id
                for task in batch.tasks
                if task.id not in first_wave
            )
            assert second_wave == [remaining_id]
            active_task_ids = set(db.scalars(select(PodLease.task_id)))
            assert active_task_ids == {first_wave[1], remaining_id}
    finally:
        engine.dispose()


def test_specified_busy_pod_waits_without_unavailable_timer():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            batch = _seed_batch(
                db,
                strategy="specified",
                pod_ids=["pod-a"],
                concurrency=1,
                task_count=1,
            )
            _seed_pod(db, "pod-a", now)
            other_case = CaseModel(
                id="case_other",
                title="其他任务",
                module=None,
                content_markdown="- 执行",
                tags=[],
                automation_level="auto",
                created_by="admin",
            )
            other = Task(
                id="task_other",
                case_id=other_case.id,
                runner_type="mobile_use",
                scenario="其他任务",
                created_by="admin",
                execution_status=ExecutionStatus.RUNNING,
                idempotency_key="other",
                request_fingerprint="{}",
                version=1,
            )
            db.add_all(
                [
                    other_case,
                    other,
                    PodLease(
                        pod_id="product-1:pod-a",
                        task_id=other.id,
                        worker_id="worker:other",
                        expires_at=now + timedelta(minutes=5),
                        version=1,
                    ),
                ]
            )
            db.commit()

            assert BatchScheduler(db).schedule(now) == []
            db.refresh(batch)
            db.refresh(batch.tasks[0])
            assert batch.unavailable_since is None
            assert batch.tasks[0].queue_reason == "waiting_for_specified_device"
    finally:
        engine.dispose()


def test_partial_specified_unavailability_uses_remaining_pod():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            batch = _seed_batch(
                db,
                strategy="specified",
                pod_ids=["pod-offline", "pod-online"],
                concurrency=2,
                task_count=2,
            )
            _seed_pod(db, "pod-offline", now, status=2)
            _seed_pod(db, "pod-online", now)

            assigned = BatchScheduler(db).schedule(now)

            assert len(assigned) == 1
            lease = db.scalar(select(PodLease))
            assert lease is not None
            assert lease.pod_id == "product-1:pod-online"
            db.refresh(batch)
            assert batch.unavailable_since is None
    finally:
        engine.dispose()


def test_all_specified_pods_unavailable_fail_queued_children_after_timeout():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            batch = _seed_batch(
                db,
                strategy="specified",
                pod_ids=["pod-offline"],
                concurrency=1,
                task_count=2,
            )
            _seed_pod(db, "pod-offline", now, status=2)

            assert BatchScheduler(db).schedule(now) == []
            db.refresh(batch)
            assert batch.unavailable_since is not None
            assert {task.queue_reason for task in batch.tasks} == {
                "device_temporarily_unavailable"
            }

            assert BatchScheduler(db).schedule(now + timedelta(seconds=301)) == []
            for task in batch.tasks:
                db.refresh(task)
                assert task.execution_status == ExecutionStatus.RESULT_READY
                assert task.verdict == Verdict.FAIL
                assert task.failure_type == "device_unavailable"
    finally:
        engine.dispose()


def test_stale_by_last_seen_starts_specified_unavailable_timer():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            batch = _seed_batch(
                db,
                strategy="specified",
                pod_ids=["pod-stale"],
                concurrency=1,
                task_count=1,
            )
            _seed_pod(db, "pod-stale", now - timedelta(minutes=4))

            assert BatchScheduler(db).schedule(now) == []

            db.refresh(batch)
            db.refresh(batch.tasks[0])
            assert batch.unavailable_since is not None
            assert (
                batch.tasks[0].queue_reason
                == "device_temporarily_unavailable"
            )
    finally:
        engine.dispose()


def test_cancelled_batch_converges_after_last_running_child_finishes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            batch = _seed_batch(
                db,
                strategy="automatic",
                pod_ids=[],
                concurrency=2,
                task_count=2,
            )
            batch.cancel_requested_at = now
            batch.execution_status = ExecutionStatus.RUNNING
            batch.tasks[0].execution_status = ExecutionStatus.RUNNING
            batch.tasks[1].execution_status = ExecutionStatus.CANCELLED
            db.commit()

            assert BatchScheduler(db).schedule(now) == []
            db.refresh(batch)
            assert batch.execution_status == ExecutionStatus.RUNNING

            batch.tasks[0].execution_status = ExecutionStatus.CANCELLED
            db.commit()
            assert BatchScheduler(db).schedule(
                now + timedelta(seconds=1)
            ) == []
            db.refresh(batch)
            assert batch.execution_status == ExecutionStatus.CANCELLED
            assert batch.verdict is None
    finally:
        engine.dispose()
