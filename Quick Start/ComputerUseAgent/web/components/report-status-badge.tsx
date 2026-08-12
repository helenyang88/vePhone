import type { ReportStatus } from "../api/types";

const LABELS: Record<ReportStatus, string> = {
  queued: "排队中",
  running: "执行中",
  success: "成功",
  failure: "失败",
  exception: "异常",
  cancelled: "已取消",
};

function tone(status: ReportStatus): string {
  if (status === "success") return "success";
  if (status === "failure" || status === "exception") return "danger";
  if (status === "running") return "running";
  if (status === "queued") return "primary";
  return "neutral";
}

export function ReportStatusBadge({ status }: { status: ReportStatus }) {
  return (
    <span className={`status-badge ${tone(status)}`}>
      <span className="dot" />
      {LABELS[status]}
    </span>
  );
}

export function reportStatusLabel(status: ReportStatus): string {
  return LABELS[status];
}
