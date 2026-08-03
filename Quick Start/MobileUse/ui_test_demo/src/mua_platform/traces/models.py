from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mua_platform.db import Base
from mua_platform.settings.models import UTCDateTime


class TaskTraceSpan(Base):
    __tablename__ = "task_trace_spans"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "stable_key",
            name="unique_task_trace_stable_key",
        ),
        UniqueConstraint(
            "task_id",
            "sequence",
            name="unique_task_trace_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )
    stable_key: Mapped[str] = mapped_column(String(160))
    parent_span_id: Mapped[str | None] = mapped_column(String(40))
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    request_id: Mapped[str | None] = mapped_column(String(128))
    step_index: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
