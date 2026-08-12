import { screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import type {
  PlanReportListResponse,
  TestPlan,
  TestPlanCaseListResponse,
} from "../../web/api/types";
import { expectCsrf, renderApp, server, user } from "./setup";

const plan: TestPlan = {
  id: "plan_1",
  name: "登录与账号核心回归",
  description: "覆盖登录和账号核心链路",
  test_type: "regression",
  tags: ["核心链路", "P0", "每日回归", "账号"].map((name, index) => ({
    name,
    foreground_color: ["#4338CA", "#0F766E", "#92400E", "#1D4ED8"][index],
    background_color: ["#4338CA1A", "#0F766E1A", "#92400E1A", "#1D4ED81A"][index],
    case_count: 1,
  })),
  case_ids: ["case_1"],
  case_count: 1,
  execution_count: 12,
  latest_execution: {
    execution_id: "execution_12",
    task_batch_id: "batch_12",
    report_status: "success",
    pass_rate: 94.44,
    created_at: "2026-07-29T12:03:00Z",
  },
  created_by: "admin",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-29T12:03:00Z",
};

const cases: TestPlanCaseListResponse = {
  items: [{
    id: "case_1",
    title: "账号密码登录",
    module: "账号",
    content_markdown: "- 登录",
    tags: ["P0"],
    automation_level: "auto",
    execution_count: 4,
    pass_count: 3,
    fail_count: 1,
    last_executed_at: "2026-07-29T12:03:00Z",
    created_by: "admin",
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-29T12:03:00Z",
  }],
  total: 11,
  page: 1,
  page_size: 10,
};

const executions: PlanReportListResponse = {
  items: Array.from({ length: 10 }, (_, index) => ({
    execution_id: `execution_${12 - index}`,
    task_batch_id: `batch_${12 - index}`,
    test_plan_id: "plan_1",
    plan_name_snapshot: plan.name,
    report_status: index === 1 ? "failure" : "success",
    pass_rate: index === 0 ? 94.44 : 90,
    created_at: `2026-07-${String(29 - index).padStart(2, "0")}T12:03:00Z`,
    started_at: `2026-07-${String(29 - index).padStart(2, "0")}T12:03:00Z`,
    finished_at: `2026-07-${String(29 - index).padStart(2, "0")}T12:04:05Z`,
    duration_seconds: 65,
  })),
  total: 12,
  page: 1,
  page_size: 10,
};

function useDetailHandlers() {
  server.use(
    http.get("/api/v1/test-plans/plan_1", () => HttpResponse.json(plan)),
    http.get("/api/v1/test-plans/plan_1/cases", ({ request }) => {
      const url = new URL(request.url);
      return HttpResponse.json({
        ...cases,
        page: Number(url.searchParams.get("page") ?? 1),
        page_size: Number(url.searchParams.get("page_size") ?? 10),
      });
    }),
    http.get("/api/v1/test-plans/plan_1/executions", () =>
      HttpResponse.json(executions)),
  );
}

it("shows compact tags, pure pass rates, ten executions, and paginated cases", async () => {
  useDetailHandlers();
  renderApp("/test-plans/plan_1");

  expect(await screen.findByRole("heading", { name: plan.name })).toBeVisible();
  expect(screen.getByText("+1")).toBeVisible();
  expect(screen.getAllByText("94.44%").length).toBeGreaterThan(0);
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(
    screen.getAllByText("2026-07-29 20:03:00").length,
  ).toBeGreaterThan(0);
  expect(screen.getAllByText("01:05").length).toBeGreaterThan(0);

  const history = screen.getByRole("table", { name: "最近十次执行" });
  expect(within(history).getAllByRole("row")).toHaveLength(11);
  expect(screen.getByRole("link", { name: "查看更多执行历史" })).toHaveAttribute(
    "href",
    "/task-reports?test_plan_id=plan_1",
  );

  const boundCases = screen.getByRole("table", { name: "绑定测试用例" });
  expect(within(boundCases).getByText("75.00%")).toBeVisible();
  await user.click(
    within(boundCases.closest("section") as HTMLElement).getByRole("button", {
      name: "下一页",
    }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("table", { name: "绑定测试用例" }),
    ).toBeVisible());
});

it("restores case pagination from the URL and browser history", async () => {
  const requests: URL[] = [];
  useDetailHandlers();
  server.use(
    http.get("/api/v1/test-plans/plan_1/cases", ({ request }) => {
      const url = new URL(request.url);
      requests.push(url);
      return HttpResponse.json({
        ...cases,
        total: 61,
        page: Number(url.searchParams.get("page") ?? 1),
        page_size: Number(url.searchParams.get("page_size") ?? 10),
      });
    }),
  );

  renderApp("/test-plans/plan_1?page=2&page_size=20", { browser: true });

  expect(await screen.findByRole("combobox", { name: "每页条数" }))
    .toHaveTextContent("20 条 / 页");
  await waitFor(() => {
    expect(requests.at(-1)?.searchParams.get("page")).toBe("2");
    expect(requests.at(-1)?.searchParams.get("page_size")).toBe("20");
  });

  await user.click(screen.getByRole("button", { name: "下一页" }));
  await waitFor(() => expect(window.location.search).toContain("page=3"));

  window.history.back();
  await waitFor(() => expect(window.location.search).toContain("page=2"));
  expect(screen.getByRole("combobox", { name: "每页条数" }))
    .toHaveTextContent("20 条 / 页");

  window.history.forward();
  await waitFor(() => expect(window.location.search).toContain("page=3"));
});

it("confirms deletion, explains report retention, and returns to the list", async () => {
  useDetailHandlers();
  let deletes = 0;
  server.use(
    http.delete("/api/v1/test-plans/plan_1", ({ request }) => {
      expectCsrf(request);
      deletes += 1;
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("/api/v1/test-plans", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 10 })),
    http.get("/api/v1/test-plans/stats", () =>
      HttpResponse.json({
        active_plan_count: 0,
        distinct_case_count: 0,
        execution_count: 12,
        latest_completed_pass_rate: 0,
      })),
  );
  renderApp("/test-plans/plan_1");

  await screen.findByRole("heading", { name: plan.name });
  await user.click(screen.getByRole("button", { name: "删除测试计划" }));
  expect(screen.getByText(/历史报告不会删除/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "确认删除" }));

  await waitFor(() => expect(deletes).toBe(1));
  expect(await screen.findByRole("heading", { name: "测试计划" })).toBeVisible();
});
