from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mua_platform.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


CASE_TEMPLATE = """## 执行任务（必填）

> 用自然语言描述要完成的任务目标

示例：

- 打开抖音APP，查看3个视频。

---

## 用例通过标准（可选）

> 明确"什么情况下算通过"，用可验证的条件表述，方便 Agent 在结果中结构化输出。

建议按「必要条件」/「可选条件」描述：

- 必要条件（全部满足）：
  - 抖音APP已成功打开。
  - 抖音APP首页显示3个视频。
- 可选增强验证（满足越多，可信度越高）：
  - 抖音APP首页每个视频都有标题。

---

## 失败判定与错误场景（可选）

> 明确"什么情况下算失败"，并列出典型异常场景，方便 Agent 在 `reason` / `content` / `struct_output` 中给出有区分度的结论。

常见失败判定：

- 页面未能进入目标位置：
  - 抖音APP首页未显示3个视频。
- 异常弹窗与系统错误：
  - 出现"网络异常""系统错误""请求过于频繁"等弹窗；
  - App 崩溃或卡死在某个 loading 界面。

---

## 前置条件 / 环境约束（可选）

> 记录对环境的显式要求，方便后续结合 `AospVersion/ImageName/ImageId`、`pod_id` 等字段排查问题。

---

## 调试备注（可选）

> 用于给未来的自己或同事一点"使用说明"。
"""


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        String(40),
        default="biz_default",
        server_default="biz_default",
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_markdown: Mapped[str] = mapped_column(Text, default=CASE_TEMPLATE)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    automation_level: Mapped[str] = mapped_column(String(32), default="manual_confirm")
    default_agent_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(100), default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
