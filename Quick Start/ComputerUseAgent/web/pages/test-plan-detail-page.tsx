import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router";

import { ApiError, api } from "../api/client";
import type {
  PlanReportListResponse,
  PlanReportSummary,
  ReportStatus,
  TestCase,
  TestPlan,
  TestPlanCaseListResponse,
} from "../api/types";
import { ConfirmDialog } from "../components/confirm-dialog";
import { MetricCard } from "../components/metric-card";
import { PageHeader } from "../components/page-header";
import { PaginationControls } from "../components/pagination-controls";
import { formatChinaDateTime, formatElapsedTime } from "../utils/time";

type PageSize = 10 | 20 | 50;

function parsePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function parsePageSize(value: string | null): PageSize {
  const parsed = Number(value);
  return parsed === 20 || parsed === 50 ? parsed : 10;
}

const STATUS_LABELS: Record<ReportStatus, string> = {
  queued: "排队中",
  running: "执行中",
  success: "成功",
  failure: "失败",
  exception: "异常",
  cancelled: "已取消",
};

function MetricIcon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

function statusTone(status: ReportStatus): string {
  if (status === "success") return "success";
  if (status === "failure" || status === "exception") return "danger";
  if (status === "running") return "running";
  if (status === "queued") return "primary";
  return "neutral";
}

function statusBadge(status: ReportStatus) {
  return (
    <span className={`status-badge ${statusTone(status)}`}>
      <span className="dot" />
      {STATUS_LABELS[status]}
    </span>
  );
}

function casePassRate(testCase: TestCase): string {
  if (!testCase.execution_count) return "-";
  return `${(
    testCase.pass_count
    / testCase.execution_count
    * 100
  ).toFixed(2)}%`;
}

export function TestPlanDetailPage() {
  const { planId = "" } = useParams<{ planId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [urlParams, setUrlParams] = useSearchParams();
  const casePage = parsePage(urlParams.get("page"));
  const casePageSize = parsePageSize(urlParams.get("page_size"));
  const [deleteOpen, setDeleteOpen] = useState(false);

  function updatePagination(
    nextPage: number,
    nextPageSize = casePageSize,
  ) {
    const next = new URLSearchParams(urlParams);
    if (nextPage <= 1) next.delete("page");
    else next.set("page", String(nextPage));
    if (nextPageSize === 10) next.delete("page_size");
    else next.set("page_size", String(nextPageSize));
    setUrlParams(next);
  }

  const plan = useQuery({
    queryKey: ["test-plan", planId],
    queryFn: () => api.get<TestPlan>(`/test-plans/${planId}`),
    enabled: Boolean(planId),
    refetchInterval: 5000,
  });
  const cases = useQuery({
    queryKey: ["test-plan-cases", planId, casePage, casePageSize],
    queryFn: () =>
      api.get<TestPlanCaseListResponse>(
        `/test-plans/${planId}/cases?page=${casePage}&page_size=${casePageSize}`,
      ),
    enabled: Boolean(planId),
  });
  const executions = useQuery({
    queryKey: ["test-plan-executions", planId],
    queryFn: () =>
      api.get<PlanReportListResponse>(
        `/test-plans/${planId}/executions?page=1&page_size=10`,
      ),
    enabled: Boolean(planId),
    refetchInterval: 5000,
  });
  const deletePlan = useMutation({
    mutationFn: () => api.delete(`/test-plans/${planId}`),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["test-plans"] }),
        queryClient.invalidateQueries({ queryKey: ["test-plan-stats"] }),
        queryClient.invalidateQueries({ queryKey: ["task-reports"] }),
      ]);
      navigate("/test-plans");
    },
  });

  if (plan.isLoading) {
    return (
      <div className="page-container test-plan-detail-page">
        <div
          className="test-plan-detail-skeleton"
          role="status"
          aria-label="正在加载测试计划详情"
          aria-live="polite"
          aria-busy="true"
        />
      </div>
    );
  }

  if (plan.isError || !plan.data) {
    const notFound = plan.error instanceof ApiError
      && plan.error.code === "test_plan_not_found";
    return (
      <div className="page-container test-plan-detail-page">
        <div className="empty-state error" role="alert">
          <strong>{notFound ? "测试计划不存在" : "测试计划加载失败"}</strong>
          <p>
            {notFound
              ? "该计划可能已被删除，历史报告仍可在测试报告中查看。"
              : "请检查网络状态后重新加载。"}
          </p>
          {notFound ? (
            <Link className="secondary-button" to="/test-plans">
              返回测试计划
            </Link>
          ) : (
            <button
              type="button"
              className="secondary-button"
              onClick={() => void plan.refetch()}
            >
              重新加载
            </button>
          )}
        </div>
      </div>
    );
  }

  const item = plan.data;
  const recent = executions.data?.items ?? [];
  const latest = recent[0] ?? null;
  const recentStatus = item.latest_execution?.report_status ?? null;

  return (
    <div className="page-container test-plan-detail-page">
      <PageHeader
        breadcrumbs={[
          { label: "首页", to: "/tasks" },
          { label: "测试计划", to: "/test-plans" },
          { label: item.name },
        ]}
        title={
          <span className="plan-detail-title">
            <span>{item.name}</span>
            <span className="plan-detail-title-tags" aria-hidden="true">
              {item.tags.slice(0, 3).map((tag) => (
                <span
                  className="registered-tag"
                  key={tag.name}
                  style={{
                    color: tag.foreground_color,
                    backgroundColor: tag.background_color,
                  }}
                >
                  {tag.name}
                </span>
              ))}
              {item.tags.length > 3 && (
                <span className="tag-more">+{item.tags.length - 3}</span>
              )}
            </span>
          </span>
        }
        description={item.description ?? "未填写计划描述"}
        actions={
          <>
            <Link
              className="secondary-button"
              to={`/test-plans/${planId}/edit`}
            >
              编辑
            </Link>
            <button
              type="button"
              className="danger-button"
              aria-label="删除测试计划"
              onClick={() => setDeleteOpen(true)}
            >
              删除
            </button>
            <Link
              className="primary-button"
              to={`/test-plans/${planId}/run`}
            >
              运行计划
            </Link>
          </>
        }
      />

      <div className="metric-grid plan-detail-metrics">
        <MetricCard
          testId="plan-detail-case-count"
          label="关联用例"
          value={item.case_count}
          meta="按固定顺序执行"
          icon={<MetricIcon path="M4 5h16v14H4zM8 9h8M8 13h5" />}
        />
        <MetricCard
          testId="plan-detail-execution-count"
          label="累计执行"
          value={item.execution_count}
          meta="全部执行历史"
          tone="running"
          icon={<MetricIcon path="M8 5v14l11-7z" />}
        />
        <MetricCard
          testId="plan-detail-latest-status"
          label="最近结果"
          value={recentStatus ? STATUS_LABELS[recentStatus] : "未执行"}
          meta="最近一次计划运行"
          tone={recentStatus === "success" ? "success" : "warning"}
          icon={<MetricIcon path="m5 12 4 4L19 6" />}
        />
        <MetricCard
          testId="plan-detail-updated"
          label="最近更新"
          value={formatChinaDateTime(item.updated_at)}
          meta="计划配置更新时间"
          tone="success"
          icon={<MetricIcon path="M12 8v4l3 2M21 12a9 9 0 1 1-9-9" />}
        />
      </div>

      <div className="test-plan-detail-stack">
        <section className="plan-detail-section">
          <div className="plan-section-heading">
            <div>
              <span className="section-kicker">最近执行</span>
              <h2>最近一次执行摘要</h2>
            </div>
          </div>
          {executions.isLoading ? (
            <div
              className="plan-inline-skeleton"
              role="status"
              aria-label="正在加载最近执行摘要"
              aria-live="polite"
              aria-busy="true"
            />
          ) : executions.isError ? (
            <InlineError onRetry={() => void executions.refetch()} />
          ) : latest ? (
            <div className="latest-execution-summary">
              <SummaryItem label="执行结果" value={statusBadge(latest.report_status)} />
              <SummaryItem
                label="测试通过率"
                value={`${latest.pass_rate.toFixed(2)}%`}
              />
              <SummaryItem
                label="总执行时长"
                value={formatElapsedTime(latest.started_at, latest.finished_at)}
              />
              <SummaryItem
                label="创建时间"
                value={formatChinaDateTime(latest.created_at)}
              />
              <Link
                className="secondary-button"
                to={`/task-reports/${latest.execution_id}`}
              >
                查看报告
              </Link>
            </div>
          ) : (
            <div className="plan-case-empty">该计划尚未执行</div>
          )}
        </section>

        <section className="plan-detail-section">
          <div className="plan-section-heading">
            <div>
              <span className="section-kicker">执行记录</span>
              <h2>最近十次执行</h2>
            </div>
            <Link
              to={`/task-reports?test_plan_id=${encodeURIComponent(planId)}`}
              className="ghost-button compact"
            >
              查看更多执行历史
            </Link>
          </div>
          {executions.isLoading ? (
            <div
              className="plan-inline-skeleton"
              role="status"
              aria-label="正在加载执行记录"
              aria-live="polite"
              aria-busy="true"
            />
          ) : executions.isError ? (
            <InlineError onRetry={() => void executions.refetch()} />
          ) : recent.length === 0 ? (
            <div className="plan-case-empty">暂无执行记录</div>
          ) : (
            <div className="table-scroll">
              <table className="data-table" aria-label="最近十次执行">
                <thead>
                  <tr>
                    <th>任务 ID</th>
                    <th>执行结果</th>
                    <th>测试通过率</th>
                    <th>创建时间</th>
                    <th>总执行时长</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((execution) => (
                    <ExecutionRow
                      key={execution.execution_id}
                      execution={execution}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="plan-detail-section">
          <div className="plan-section-heading">
            <div>
              <span className="section-kicker">计划范围</span>
              <h2>绑定测试用例</h2>
            </div>
          </div>
          {cases.isLoading ? (
            <div
              className="plan-inline-skeleton"
              role="status"
              aria-label="正在加载绑定用例"
              aria-live="polite"
              aria-busy="true"
            />
          ) : cases.isError ? (
            <InlineError onRetry={() => void cases.refetch()} />
          ) : (cases.data?.items.length ?? 0) === 0 ? (
            <div className="plan-case-empty">暂无绑定用例</div>
          ) : (
            <div className="table-scroll">
              <table className="data-table" aria-label="绑定测试用例">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>用例名称</th>
                    <th>用例 ID</th>
                    <th>模块</th>
                    <th>通过率</th>
                    <th>最近执行</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.data?.items.map((testCase, index) => (
                    <tr key={testCase.id}>
                      <td>{(casePage - 1) * casePageSize + index + 1}</td>
                      <td>{testCase.title}</td>
                      <td className="monospace" translate="no">{testCase.id}</td>
                      <td>{testCase.module ?? "-"}</td>
                      <td>{casePassRate(testCase)}</td>
                      <td>{formatChinaDateTime(testCase.last_executed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!cases.isLoading && !cases.isError && (
            <PaginationControls
              page={casePage}
              pageSize={casePageSize}
              total={cases.data?.total ?? 0}
              onPageChange={(value) => updatePagination(value)}
              onPageSizeChange={(value) => updatePagination(1, value)}
            />
          )}
        </section>
      </div>

      <ConfirmDialog
        open={deleteOpen}
        title="删除测试计划"
        description="删除后计划将无法继续运行，但历史报告不会删除，仍可在测试报告中查看。"
        confirmLabel="确认删除"
        pendingLabel="正在删除…"
        isPending={deletePlan.isPending}
        errorMessage={deletePlan.isError ? "删除失败，请稍后重试。" : ""}
        onClose={() => {
          if (!deletePlan.isPending) setDeleteOpen(false);
        }}
        onConfirm={() => {
          if (!deletePlan.isPending) deletePlan.mutate();
        }}
      />
    </div>
  );
}

function ExecutionRow({ execution }: { execution: PlanReportSummary }) {
  return (
    <tr>
      <td>
        <Link
          to={`/task-reports/${execution.execution_id}`}
          translate="no"
        >
          {execution.task_batch_id}
        </Link>
      </td>
      <td>{statusBadge(execution.report_status)}</td>
      <td>{execution.pass_rate.toFixed(2)}%</td>
      <td>{formatChinaDateTime(execution.created_at)}</td>
      <td>{formatElapsedTime(execution.started_at, execution.finished_at)}</td>
    </tr>
  );
}

function SummaryItem({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="latest-summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InlineError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="plan-case-empty error" role="alert">
      <span>数据加载失败，请稍后重试。</span>
      <button type="button" className="secondary-button" onClick={onRetry}>
        重新加载
      </button>
    </div>
  );
}
