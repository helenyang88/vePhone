from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mua_platform.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class TestPlan(Base):
    __tablename__ = "test_plans"
    __table_args__ = (
        Index(
            "uq_active_test_plan_name_key",
            "name_key",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_type: Mapped[str] = mapped_column(String(32), default="regression")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cases: Mapped[list["TestPlanCase"]] = relationship(
        cascade="all, delete-orphan",
        order_by="TestPlanCase.position",
    )


class TestPlanCase(Base):
    __tablename__ = "test_plan_cases"
    __table_args__ = (
        UniqueConstraint("plan_id", "case_id"),
        UniqueConstraint("plan_id", "position"),
    )

    plan_id: Mapped[str] = mapped_column(
        ForeignKey("test_plans.id"),
        primary_key=True,
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("test_cases.id"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer)


class PlanExecution(Base):
    __tablename__ = "plan_executions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    test_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("test_plans.id"),
        nullable=True,
        index=True,
    )
    task_batch_id: Mapped[str] = mapped_column(
        ForeignKey("task_batches.id"),
        unique=True,
        index=True,
    )
    plan_name_snapshot: Mapped[str] = mapped_column(String(100))
    plan_tags_snapshot: Mapped[list[str]] = mapped_column(JSON, default=list)
    case_ids_snapshot: Mapped[list[str]] = mapped_column(JSON)
    device_strategy_snapshot: Mapped[str] = mapped_column(String(32))
    pod_ids_snapshot: Mapped[list[str]] = mapped_column(JSON, default=list)
    concurrency_snapshot: Mapped[int] = mapped_column(Integer)
    runner_type_snapshot: Mapped[str] = mapped_column(String(32))
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


class TagColorRegistry(Base):
    __tablename__ = "tag_color_registry"

    tag_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    foreground_color: Mapped[str] = mapped_column(String(7), unique=True)
    background_color: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
