from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from mua_platform.db import Base

DEFAULT_BUSINESS_ID = "biz_default"
DEFAULT_BUSINESS_NAME = "默认业务"


def utc_now() -> datetime:
    return datetime.now(UTC)


class BusinessSpace(Base):
    __tablename__ = "business_spaces"
    __table_args__ = (
        Index(
            "uq_active_business_space_name_key",
            "name_key",
            unique=True,
            sqlite_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    task_concurrency_limit: Mapped[int] = mapped_column(
        Integer,
        default=4,
        server_default="4",
    )
    created_by: Mapped[str] = mapped_column(String(100), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
