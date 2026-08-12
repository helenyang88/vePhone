import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from mua_platform.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, index=True)
    details_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


def add_runner_settings_audit(
    db: Session,
    *,
    actor_user_id: int,
    mode: str,
    changed_fields: list[str],
) -> None:
    details_json = json.dumps(
        {
            "mode": mode,
            "changed_fields": sorted(changed_fields),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    db.add(
        AuditEvent(
            id=f"audit_{uuid4().hex}",
            action="runner_settings_updated",
            actor_user_id=actor_user_id,
            details_json=details_json,
        )
    )
