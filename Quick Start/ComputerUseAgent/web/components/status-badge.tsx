import type { ExecutionStatus, Verdict } from "../api/types";

const STATUS_LABELS: Record<ExecutionStatus, string> = {
  queued: "排队中",
  running: "执行中",
  result_ready: "已完成",
  cancelled: "已取消",
};

const VERDICT_LABELS: Record<Verdict, string> = {
  pass: "成功",
  fail: "失败",
};

export function StatusBadge({
  status,
  verdict,
}: {
  status?: string;
  verdict?: string | null;
}) {
  const value = status ?? verdict;
  if (!value) {
    return (
      <span className="status-badge neutral">
        <span className="dot" />
        未判定
      </span>
    );
  }

  const isExecutionStatus = (v: string): v is ExecutionStatus =>
    v in STATUS_LABELS;
  const isVerdict = (v: string): v is Verdict => v in VERDICT_LABELS;

  const label = status && isExecutionStatus(status)
    ? STATUS_LABELS[status]
    : verdict && isVerdict(verdict)
      ? VERDICT_LABELS[verdict]
      : value;
  const tone =
    value === "pass" || value === "result_ready"
      ? "success"
      : value === "fail"
        ? "danger"
        : value === "running"
          ? "running"
          : value === "queued"
            ? "primary"
            : "neutral";

  return (
    <span className={`status-badge ${tone}`}>
      <span className="dot" />
      {label}
    </span>
  );
}
