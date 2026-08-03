from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mua_platform.pods.models import POD_STATUS_RUNNING, DiscoveredPod
from mua_platform.tasks.batches import aggregate_batch_status
from mua_platform.tasks.models import PodLease, Task, TaskBatch
from mua_platform.tasks.repository import SQLiteTaskRepository
from mua_platform.tasks.state_machine import ExecutionStatus

POD_FRESHNESS_WINDOW = timedelta(seconds=180)


class BatchScheduler:
    def __init__(
        self,
        db: Session,
        *,
        reservation_ttl: timedelta = timedelta(minutes=5),
    ):
        self.db = db
        self.reservation_ttl = reservation_ttl

    def schedule(self, now: datetime) -> list[str]:
        repository = SQLiteTaskRepository(self.db)
        repository.release_expired_leases(now)
        assigned: list[str] = []
        batches = list(
            self.db.scalars(
                select(TaskBatch)
                .options(selectinload(TaskBatch.tasks))
                .where(
                    TaskBatch.execution_status.in_(
                        [ExecutionStatus.QUEUED, ExecutionStatus.RUNNING]
                    ),
                )
                .order_by(TaskBatch.created_at, TaskBatch.id)
            )
        )
        for batch in batches:
            assigned.extend(self._schedule_batch(batch, now, repository))
        return assigned

    def _schedule_batch(
        self,
        batch: TaskBatch,
        now: datetime,
        repository: SQLiteTaskRepository,
    ) -> list[str]:
        if batch.cancel_requested_at is not None:
            aggregate_batch_status(batch, now)
            self.db.commit()
            return []
        queued = [
            task
            for task in batch.tasks
            if task.execution_status == ExecutionStatus.QUEUED
        ]
        if not queued:
            aggregate_batch_status(batch, now)
            self.db.commit()
            return []

        product_id = batch.config_snapshot.get("product_id")
        if not isinstance(product_id, str) or not product_id:
            self._set_reason(queued, "waiting_for_any_device")
            self.db.commit()
            return []

        active_leases = list(
            self.db.scalars(select(PodLease).where(PodLease.expires_at > now))
        )
        lease_by_task = {lease.task_id: lease for lease in active_leases}
        leased_keys = {lease.pod_id for lease in active_leases}
        occupied = sum(
            task.execution_status == ExecutionStatus.RUNNING
            or task.id in lease_by_task
            for task in batch.tasks
        )
        slots = max(0, batch.concurrency - occupied)
        unreserved = [task for task in queued if task.id not in lease_by_task]
        if slots == 0:
            self._set_reason(unreserved, "waiting_for_capacity")
            self.db.commit()
            return []

        rows = list(
            self.db.scalars(
                select(DiscoveredPod)
                .where(DiscoveredPod.product_id == product_id)
                .order_by(DiscoveredPod.last_assigned_at.asc().nullsfirst())
            )
        )
        row_by_id = {row.pod_id: row for row in rows}
        requested_ids = (
            list(batch.pod_ids)
            if batch.device_strategy == "specified"
            else [row.pod_id for row in rows]
        )
        hard_unavailable = {
            pod_id
            for pod_id in requested_ids
            if self._hard_unavailable(row_by_id.get(pod_id), now)
        }
        available = [
            row_by_id[pod_id]
            for pod_id in requested_ids
            if pod_id in row_by_id
            and pod_id not in hard_unavailable
            and f"{product_id}:{pod_id}" not in leased_keys
            and pod_id not in leased_keys
        ]

        if batch.device_strategy == "specified":
            all_hard_unavailable = bool(requested_ids) and len(
                hard_unavailable
            ) == len(requested_ids)
            if all_hard_unavailable:
                return self._handle_all_unavailable(
                    batch,
                    queued,
                    now,
                    repository,
                )
            if batch.unavailable_since is not None:
                batch.unavailable_since = None

        newly_assigned: list[str] = []
        for task, pod in zip(unreserved[:slots], available[:slots], strict=False):
            if repository.reserve_batch_pod(
                task.id,
                product_id,
                pod.pod_id,
                now,
                self.reservation_ttl,
            ):
                newly_assigned.append(task.id)
                leased_keys.add(f"{product_id}:{pod.pod_id}")

        remaining = [
            task for task in unreserved if task.id not in set(newly_assigned)
        ]
        if remaining:
            if len(newly_assigned) >= slots:
                reason = "waiting_for_capacity"
            elif batch.device_strategy == "specified":
                reason = "waiting_for_specified_device"
            else:
                reason = "waiting_for_any_device"
            self._set_reason(remaining, reason)
            self.db.commit()
        return newly_assigned

    def _handle_all_unavailable(
        self,
        batch: TaskBatch,
        queued: list[Task],
        now: datetime,
        repository: SQLiteTaskRepository,
    ) -> list[str]:
        self._set_reason(queued, "device_temporarily_unavailable")
        if batch.unavailable_since is None:
            batch.unavailable_since = now
            self.db.commit()
            return []
        unavailable_since = _aware(batch.unavailable_since)
        if now - unavailable_since < timedelta(
            seconds=batch.device_wait_timeout_seconds
        ):
            self.db.commit()
            return []
        task_ids = [task.id for task in queued]
        self.db.commit()
        for task_id in task_ids:
            repository.finalize_device_unavailable(task_id)
        self.db.expire_all()
        refreshed = self.db.scalar(
            select(TaskBatch)
            .options(selectinload(TaskBatch.tasks))
            .where(TaskBatch.id == batch.id)
        )
        if refreshed is not None:
            aggregate_batch_status(refreshed, now)
            self.db.commit()
        return []

    @staticmethod
    def _set_reason(tasks: list[Task], reason: str) -> None:
        for task in tasks:
            task.queue_reason = reason

    @staticmethod
    def _hard_unavailable(
        pod: DiscoveredPod | None,
        now: datetime,
    ) -> bool:
        if pod is None:
            return True
        if pod.discovery_state != "active":
            return True
        if pod.pod_status_code != POD_STATUS_RUNNING:
            return True
        if now - _aware(pod.last_seen_at) > POD_FRESHNESS_WINDOW:
            return True
        return pod.cooldown_until is not None and _aware(pod.cooldown_until) > now


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
