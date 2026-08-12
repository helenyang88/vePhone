from datetime import datetime

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mua_platform.db import Base
from mua_platform.settings.models import UTCDateTime
from mua_platform.tasks.models import utc_now


class PodPoolRefresh(Base):
    __tablename__ = "pod_pool_refreshes"

    product_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    refreshed_at: Mapped[datetime] = mapped_column(UTCDateTime())


POD_STATUS_CREATING = 1
POD_STATUS_RUNNING = 2
POD_STATUS_OCCUPIED = 3
POD_STATUS_ABNORMAL = 4
POD_STATUS_UPGRADING = 5
POD_STATUS_UPGRADE_FAILED = 6
POD_STATUS_REMOVING = 7
POD_STATUS_REMOVE_FAILED = 8

STREAM_STATUS_IDLE = 0
STREAM_STATUS_STREAMING = 1
STREAM_STATUS_READY = 2


class DiscoveredPod(Base):
    __tablename__ = "discovered_pods"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "pod_id",
            name="unique_discovered_product_pod",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(255), index=True)
    pod_id: Mapped[str] = mapped_column(String(255))
    pod_name: Mapped[str] = mapped_column(String(255))
    pod_status_code: Mapped[int] = mapped_column(Integer, default=POD_STATUS_RUNNING)
    stream_status: Mapped[int | None] = mapped_column(Integer)
    discovery_state: Mapped[str] = mapped_column(String(16), default="active")
    image_id: Mapped[str | None] = mapped_column(String(255))
    image_name: Mapped[str | None] = mapped_column(String(255))
    aosp_version: Mapped[str | None] = mapped_column(String(32))
    display_layout_id: Mapped[str | None] = mapped_column(String(64))
    dc_id: Mapped[str | None] = mapped_column(String(64))
    dc_name: Mapped[str | None] = mapped_column(String(128))
    isp_code: Mapped[int | None] = mapped_column(Integer)
    region: Mapped[str | None] = mapped_column(String(32))
    zone_id: Mapped[str | None] = mapped_column(String(64))
    config_code: Mapped[str | None] = mapped_column(String(64))
    config_name: Mapped[str | None] = mapped_column(String(64))
    config_type: Mapped[int | None] = mapped_column(Integer)
    server_type_code: Mapped[str | None] = mapped_column(String(64))
    intranet_ip: Mapped[str | None] = mapped_column(String(64))
    adb_address: Mapped[str | None] = mapped_column(String(128))
    adb_status: Mapped[int | None] = mapped_column(Integer)
    data_size: Mapped[str | None] = mapped_column(String(32))
    data_size_used: Mapped[str | None] = mapped_column(String(32))
    pod_created_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    node_id: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(64))
    project_name: Mapped[str | None] = mapped_column(String(128))
    public_ip: Mapped[str | None] = mapped_column(String(64))
    os_type: Mapped[str | None] = mapped_column(String(64))
    os_name: Mapped[str | None] = mapped_column(String(255))
    instance_type: Mapped[str | None] = mapped_column(String(128))
    vcpu: Mapped[int | None] = mapped_column(Integer)
    memory_gib: Mapped[int | None] = mapped_column(Integer)
    specification: Mapped[str | None] = mapped_column(String(255))
    agent_endpoint: Mapped[str | None] = mapped_column(String(255))
    plugin_version: Mapped[str | None] = mapped_column(String(64))
    script_version: Mapped[str | None] = mapped_column(String(64))
    status_name: Mapped[str | None] = mapped_column(String(64))
    status_message: Mapped[str | None] = mapped_column(String(255))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    node_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_request_id: Mapped[str | None] = mapped_column(String(128))
    last_assigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def online(self) -> bool:
        return self.pod_status_code == POD_STATUS_RUNNING

    @property
    def remote_status(self) -> str:
        return _REMOTE_STATUS_LABELS.get(self.pod_status_code, "unknown")


_REMOTE_STATUS_LABELS: dict[int, str] = {
    POD_STATUS_CREATING: "creating",
    POD_STATUS_RUNNING: "running",
    POD_STATUS_OCCUPIED: "occupied",
    POD_STATUS_ABNORMAL: "abnormal",
    POD_STATUS_UPGRADING: "upgrading",
    POD_STATUS_UPGRADE_FAILED: "upgrade_failed",
    POD_STATUS_REMOVING: "removing",
    POD_STATUS_REMOVE_FAILED: "remove_failed",
}
