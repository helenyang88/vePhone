import type { ReactNode } from "react";

export type MetricTone = "primary" | "running" | "warning" | "success";

export function MetricCard({
  testId,
  label,
  value,
  meta,
  tone = "primary",
  icon,
}: {
  testId: string;
  label: string;
  value: ReactNode;
  meta: string;
  tone?: MetricTone;
  icon: ReactNode;
}) {
  return (
    <article className={`metric-card ${tone}`} data-testid={testId}>
      <div className="metric-card-icon">{icon}</div>
      <div className="metric-card-content">
        <span className="metric-card-label">{label}</span>
        <strong className="metric-card-value">{value}</strong>
        <span className="metric-card-meta">{meta}</span>
      </div>
    </article>
  );
}
