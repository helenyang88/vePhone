import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../api/client";
import type {
  CaseStats,
  ModuleListResponse,
  TagListResponse,
  Task,
  TestCase,
  TestCaseListResponse,
} from "../api/types";
import { ConfirmDialog } from "../components/confirm-dialog";
import { CopyButton } from "../components/copy-button";
import { ExecuteDialog, type ExecuteConfig } from "../components/execute-dialog";
import { MetricCard } from "../components/metric-card";
import { PageHeader } from "../components/page-header";
import { PaginationControls } from "../components/pagination-controls";
import { SingleSelect } from "../components/single-select";
import { formatChinaDate, formatChinaDateTime, parseTimestampMs } from "../utils/time";

const PAGE_SIZE = 10;

function formatRelativeTime(value: string | null): string {
  if (!value) return "从未执行";
  const ms = parseTimestampMs(value);
  if (Number.isNaN(ms)) return "从未执行";
  const diffMs = Date.now() - ms;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay}天前`;
  return formatChinaDate(value);
}

function passRate(c: TestCase): number {
  if (c.execution_count === 0) return 0;
  return Math.round((c.pass_count / c.execution_count) * 100);
}

function initialPage(params: URLSearchParams): number {
  const value = Number(params.get("page") ?? "1");
  return Number.isInteger(value) && value > 0 ? value : 1;
}

function tagToneClass(tag: string): string {
  let hash = 7;
  for (const char of tag) {
    hash = (hash * 33 + char.charCodeAt(0)) >>> 0;
  }
  return `tag-tone-${hash % 5}`;
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M12 5v14" />
    </svg>
  );
}

function ImportIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 21h16" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="6 3 20 12 6 21 6 3" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function DuplicateIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="13" height="13" x="9" y="9" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
    </svg>
  );
}

function AutomationIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m13 2-2 2.5h3L12 7" />
      <rect width="18" height="13" x="3" y="8" rx="2" />
      <path d="M8 13h.01M16 13h.01M9 17h6" />
    </svg>
  );
}

function RunsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12h4l3-9 4 18 3-9h4" />
    </svg>
  );
}

function PassRateIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <path d="m9 11 3 3L22 4" />
    </svg>
  );
}

export function CasesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [urlParams, setUrlParams] = useSearchParams();
  const [page, setPage] = useState(() => initialPage(urlParams));
  const [search, setSearch] = useState(() => urlParams.get("search") ?? "");
  const [searchInput, setSearchInput] = useState(
    () => urlParams.get("search") ?? "",
  );
  const [moduleFilter, setModuleFilter] = useState<string>(
    () => urlParams.get("module") ?? "",
  );
  const [tagFilter, setTagFilter] = useState<string>(
    () => urlParams.get("tag") ?? "",
  );
  const [execDialogOpen, setExecDialogOpen] = useState(false);
  const [execCase, setExecCase] = useState<TestCase | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TestCase | null>(null);
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");

  const queryParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("page_size", String(PAGE_SIZE));
    if (search) params.set("search", search);
    if (moduleFilter) params.set("module", moduleFilter);
    if (tagFilter) params.set("tag", tagFilter);
    return params.toString();
  }, [page, search, moduleFilter, tagFilter]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (page > 1) params.set("page", String(page));
    if (search) params.set("search", search);
    if (moduleFilter) params.set("module", moduleFilter);
    if (tagFilter) params.set("tag", tagFilter);
    setUrlParams(params, { replace: true });
  }, [
    moduleFilter,
    page,
    search,
    setUrlParams,
    tagFilter,
  ]);

  const casesQuery = useQuery({
    queryKey: ["cases", queryParams],
    queryFn: () => api.get<TestCaseListResponse>(`/cases?${queryParams}`),
    refetchInterval: 5000,
  });

  const statsQuery = useQuery({
    queryKey: ["case-stats"],
    queryFn: () => api.get<CaseStats>("/cases/stats"),
    refetchInterval: 5000,
  });

  const tagsQuery = useQuery({
    queryKey: ["case-tags"],
    queryFn: () => api.get<TagListResponse>("/cases/tags"),
  });

  const modulesQuery = useQuery({
    queryKey: ["case-modules"],
    queryFn: () => api.get<ModuleListResponse>("/cases/modules"),
  });

  const deleteCase = useMutation({
    mutationFn: (caseId: string) => api.delete(`/cases/${caseId}`),
    onMutate: () => {
      setActionError("");
      setActionMessage("");
    },
    onSuccess: () => {
      setDeleteTarget(null);
      setActionMessage("用例已删除。");
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
      void queryClient.invalidateQueries({ queryKey: ["case-stats"] });
      void queryClient.invalidateQueries({ queryKey: ["case-tags"] });
      void queryClient.invalidateQueries({ queryKey: ["case-modules"] });
    },
    onError: (error) => {
      setActionError(
        error instanceof ApiError && error.code === "case_has_tasks"
          ? "该用例已有执行记录，为保留任务历史暂不能删除。"
          : error instanceof ApiError
          ? `${error.message}，请刷新页面后重试。`
          : "删除用例失败，请刷新页面后重试。",
      );
    },
  });

  const copyCase = useMutation({
    mutationFn: (caseId: string) =>
      api.post<TestCase>(`/cases/${caseId}/copy`),
    onMutate: () => {
      setActionError("");
      setActionMessage("");
    },
    onSuccess: (copied) => {
      setActionMessage(`已创建副本「${copied.title}」。`);
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
      void queryClient.invalidateQueries({ queryKey: ["case-stats"] });
      void queryClient.invalidateQueries({ queryKey: ["case-tags"] });
      void queryClient.invalidateQueries({ queryKey: ["case-modules"] });
    },
    onError: (error) => {
      setActionError(
        error instanceof ApiError
          ? `${error.message}，请稍后重试。`
          : "复制用例失败，请稍后重试。",
      );
    },
  });

  const executeCase = useMutation({
    mutationFn: ({ caseId, config }: { caseId: string; config: ExecuteConfig }) =>
      api.post<Task>(`/cases/${caseId}/execute`, {
        idempotency_key: `exec_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        pod_id: config.pod_id,
        timeout_seconds: config.timeout_seconds,
        agent_config_mode: config.agent_config_mode,
        agent_options: config.agent_options,
      }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
      void queryClient.invalidateQueries({ queryKey: ["pod-pool"] });
      setExecDialogOpen(false);
      navigate(`/tasks/${data.id}`);
    },
  });

  const totalItems = casesQuery.data?.total ?? 0;
  const items = casesQuery.data?.items ?? [];
  const kpi = statsQuery.data ?? {
    total: 0,
    auto_count: 0,
    today_executions: 0,
    total_executions: 0,
    pass_rate: 0,
  };
  const hasFilter = Boolean(search || moduleFilter || tagFilter);
  const moduleOptions = useMemo(
    () => [
      { value: "", label: "全部模块" },
      ...(modulesQuery.data?.items ?? []).map((module) => ({
        value: module,
        label: module,
      })),
    ],
    [modulesQuery.data?.items],
  );
  const tagOptions = useMemo(
    () => [
      { value: "", label: "全部标签" },
      ...(tagsQuery.data?.items ?? []).map((tag) => ({
        value: tag,
        label: tag,
      })),
    ],
    [tagsQuery.data?.items],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  function handleFilterChange(type: "module" | "tag", value: string) {
    setPage(1);
    if (type === "module") setModuleFilter(value);
    if (type === "tag") setTagFilter(value);
  }

  return (
    <div className="page-container cases-page">
      <PageHeader
        breadcrumbs={[{ label: "首页", to: "/tasks" }, { label: "用例库" }]}
        title="用例库"
        description="管理所有 Markdown 格式的自动化测试用例"
        actions={
          <>
            <Link to="/cases/import/preview" className="secondary-button">
              <ImportIcon />
              <span>导入用例</span>
            </Link>
            <Link to="/cases/new" className="primary-button">
              <PlusIcon />
              <span>新建用例</span>
            </Link>
          </>
        }
      />
      <div className="metric-grid case-metric-grid">
        <MetricCard
          testId="case-metric-total"
          label="用例总数"
          value={kpi.total}
          meta="全部测试资产"
          icon={<BookIcon />}
        />
        <MetricCard
          testId="case-metric-today"
          label="今日执行"
          value={kpi.today_executions}
          meta="中国时区今日"
          tone="success"
          icon={<AutomationIcon />}
        />
        <MetricCard
          testId="case-metric-executions"
          label="累计执行"
          value={kpi.total_executions}
          meta="全部历史执行"
          tone="running"
          icon={<RunsIcon />}
        />
        <MetricCard
          testId="case-metric-pass-rate"
          label="通过率"
          value={`${kpi.pass_rate}%`}
          meta="全部已执行用例"
          tone="warning"
          icon={<PassRateIcon />}
        />
      </div>
      <div className="page-content case-content-compact">
        {actionMessage && (
          <div className="case-action-message" aria-live="polite">
            {actionMessage}
          </div>
        )}
        {actionError && (
          <div className="error-banner" role="alert">
            {actionError}
          </div>
        )}
        <div className="filter-card">
          <div className="case-filter-toolbar task-filter-bar">
            <div className="case-filter-search task-search">
              <SearchIcon />
              <input
                aria-label="搜索用例"
                autoComplete="off"
                name="case-search"
                type="search"
                placeholder="搜索用例名称、ID 或模块…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </div>
            <SingleSelect
              label="模块筛选"
              value={moduleFilter}
              options={moduleOptions}
              onChange={(value) => handleFilterChange("module", value)}
            />
            <SingleSelect
              label="标签筛选"
              value={tagFilter}
              options={tagOptions}
              onChange={(value) => handleFilterChange("tag", value)}
            />
            {(search || moduleFilter || tagFilter) && (
              <button
                type="button"
                className="text-button"
                aria-label="重置筛选"
                onClick={() => {
                  setSearch("");
                  setSearchInput("");
                  setModuleFilter("");
                  setTagFilter("");
                  setPage(1);
                }}
              >
                重置筛选
              </button>
            )}
          </div>
        </div>

        <div className="table-card">
          {casesQuery.isLoading ? (
            <div className="empty-state">加载中…</div>
          ) : casesQuery.isError ? (
            <div className="empty-state error">
              加载失败：{casesQuery.error instanceof ApiError ? casesQuery.error.message : "未知错误"}
            </div>
          ) : items.length === 0 ? (
            hasFilter ? (
              <div className="empty-state">
                <p>无匹配结果，请调整搜索条件或表头筛选</p>
              </div>
            ) : (
              <div className="empty-state">
                <p>暂无用例</p>
                <Link to="/cases/new" className="primary-button" style={{ marginTop: 12 }}>
                  <PlusIcon />
                  <span>创建第一个用例</span>
                </Link>
              </div>
            )
          ) : (
            <div className="table-scroll">
              <table className="data-table task-table cases-table">
                <thead>
                  <tr>
                    <th className="sticky-col case-sticky-header" style={{ minWidth: 280 }}>用例ID</th>
                    <th style={{ minWidth: 200 }}>用例名称</th>
                    <th style={{ width: 100 }}>模块</th>
                    <th style={{ minWidth: 160 }}>标签</th>
                    <th style={{ width: 80 }}>执行次数</th>
                    <th style={{ width: 80 }}>通过率</th>
                    <th style={{ width: 130 }}>最近执行</th>
                    <th style={{ width: 80 }}>创建人</th>
                    <th style={{ width: 100 }}>更新时间</th>
                    <th className="case-actions-cell" style={{ width: 160 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => {
                    const rate = passRate(c);
                    return (
                      <tr key={c.id}>
                        <td className="sticky-col">
                          <div className="cell-id-copy">
                            <span
                              className="monospace cell-id-full"
                              translate="no"
                              style={{ fontSize: "0.75rem", color: "var(--mua-neutral-500)" }}
                              title={c.id}
                            >
                              {c.id}
                            </span>
                            <CopyButton value={c.id} label="用例ID" />
                          </div>
                        </td>
                        <td>
                          <span className="case-name-wrapper" data-full-title={c.title}>
                            <Link to={`/cases/${c.id}/edit`} className="case-name-link case-name-link-neutral">
                              {c.title}
                            </Link>
                          </span>
                        </td>
                        <td className="cell-truncate" style={{ fontSize: "0.8rem" }}>
                          {c.module || <span style={{ color: "var(--mua-neutral-400)" }}>—</span>}
                        </td>
                        <td>
                          <div className="tag-list">
                            {c.tags.slice(0, 3).map((t) => (
                              <button
                                key={t}
                                type="button"
                                className={`tag tag-clickable ${tagToneClass(t)}${tagFilter === t ? " tag-active" : ""}`}
                                title={tagFilter === t ? `取消筛选「${t}」` : `按标签「${t}」筛选`}
                                onClick={() => handleFilterChange("tag", tagFilter === t ? "" : t)}
                              >
                                {t}
                              </button>
                            ))}
                            {c.tags.length > 3 && (
                              <span className="tag-more">+{c.tags.length - 3}</span>
                            )}
                            {c.tags.length === 0 && <span style={{ color: "var(--mua-neutral-400)", fontSize: "0.8rem" }}>—</span>}
                          </div>
                        </td>
                        <td className="case-number-cell">
                          {c.execution_count}
                        </td>
                        <td className="case-number-cell">
                          <span className={`case-rate ${rate >= 80 ? "success" : rate >= 50 ? "warning" : "danger"}`}>
                            {rate}%
                          </span>
                        </td>
                        <td>
                          {c.last_executed_at ? (
                            <span
                              className="case-relative-time"
                              title={formatChinaDateTime(c.last_executed_at)}
                            >
                              {formatRelativeTime(c.last_executed_at)}
                            </span>
                          ) : (
                            <span className="case-empty-value">从未执行</span>
                          )}
                        </td>
                        <td>
                          <span className="case-owner-text">{c.created_by}</span>
                        </td>
                        <td style={{ fontSize: "0.75rem", color: "var(--mua-neutral-500)", whiteSpace: "nowrap" }}>
                          {formatChinaDateTime(c.updated_at)}
                        </td>
                        <td className="case-actions-cell">
                          <div className="row-actions case-row-actions">
                            <button
                              type="button"
                              className="icon-action"
                              title="执行用例"
                              aria-label="执行用例"
                              onClick={() => { setExecCase(c); setExecDialogOpen(true); }}
                              disabled={executeCase.isPending}
                            >
                              <PlayIcon />
                            </button>
                            <Link
                              to={`/cases/${c.id}/edit`}
                              className="icon-action"
                              title="编辑用例"
                              aria-label="编辑用例"
                            >
                              <EditIcon />
                            </Link>
                            <button
                              type="button"
                              className="icon-action"
                              title="复制用例"
                              aria-label="复制用例"
                              onClick={() => copyCase.mutate(c.id)}
                              disabled={copyCase.isPending}
                            >
                              <DuplicateIcon />
                            </button>
                            <button
                              type="button"
                              className="icon-action danger"
                              title="删除用例"
                              aria-label="删除用例"
                              onClick={() => setDeleteTarget(c)}
                              disabled={deleteCase.isPending}
                            >
                              <TrashIcon />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!casesQuery.isLoading && !casesQuery.isError && (
            <PaginationControls
              page={page}
              pageSize={PAGE_SIZE}
              total={totalItems}
              onPageChange={setPage}
              onPageSizeChange={() => setPage(1)}
              showPageSize={false}
            />
          )}
        </div>
      </div>

      <ExecuteDialog
        open={execDialogOpen}
        caseTitle={execCase?.title ?? ""}
        onClose={() => { setExecDialogOpen(false); setExecCase(null); }}
        onConfirm={(config) => {
          if (execCase) executeCase.mutate({ caseId: execCase.id, config });
        }}
        isPending={executeCase.isPending}
        allowCaseDefault={Boolean(execCase?.default_agent_options)}
        errorMessage={
          executeCase.error instanceof ApiError
            ? `${executeCase.error.message}，请检查设备与执行配置后重试。`
            : executeCase.isError
              ? "创建任务失败，请检查设备与执行配置后重试。"
              : ""
        }
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除用例"
        description={deleteTarget
          ? `确定删除「${deleteTarget.title}」吗？删除后无法恢复。`
          : ""}
        confirmLabel="确认删除"
        pendingLabel="删除中…"
        isPending={deleteCase.isPending}
        errorMessage={deleteCase.isError ? actionError : ""}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteCase.mutate(deleteTarget.id);
        }}
      />
    </div>
  );
}
