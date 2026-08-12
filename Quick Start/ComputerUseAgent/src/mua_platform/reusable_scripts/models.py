from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mua_platform.cases.models import ScriptVersion
from mua_platform.db import Base
from mua_platform.tasks.models import Task


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReusableScript(Base):
    __tablename__ = "reusable_scripts"
    __table_args__ = (
        UniqueConstraint("source_task_id", "idempotency_key", name="unique_reusable_save"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    source_script_version_id: Mapped[str] = mapped_column(
        ForeignKey("script_versions.id")
    )
    current_version_id: Mapped[str] = mapped_column(ForeignKey("script_versions.id"))
    app_name: Mapped[str] = mapped_column(String(255))
    app_package: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    source_task: Mapped[Task] = relationship(foreign_keys=[source_task_id])
    source_script_version: Mapped[ScriptVersion] = relationship(
        foreign_keys=[source_script_version_id]
    )
    script_version: Mapped[ScriptVersion] = relationship(
        foreign_keys=[current_version_id]
    )
