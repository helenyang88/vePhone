import { screen } from "@testing-library/react";
import { delay, HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import type { TestPlan } from "../../web/api/types";
import { renderApp, server } from "./setup";

const plan: TestPlan = {
  id: "plan_1",
  name: "核心回归",
  description: null,
  test_type: "regression",
  tags: [],
  case_ids: ["case_1"],
  case_count: 1,
  execution_count: 0,
  latest_execution: null,
  created_by: "admin",
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:00Z",
};

async function pendingJson() {
  await delay("infinite");
  return HttpResponse.json({});
}

async function expectLoading(name: string) {
  const loading = await screen.findByRole("status", { name });
  expect(loading).toHaveAttribute("aria-live", "polite");
  expect(loading).toHaveAttribute("aria-busy", "true");
}

it("announces the test plan list loading state", async () => {
  server.use(
    http.get("/api/v1/test-plans", pendingJson),
    http.get("/api/v1/test-plans/stats", () =>
      HttpResponse.json({
        active_plan_count: 0,
        distinct_case_count: 0,
        execution_count: 0,
        latest_completed_pass_rate: 0,
      })),
    http.get("/api/v1/test-plans/tags", () =>
      HttpResponse.json({ items: [] })),
  );
  renderApp("/test-plans");
  await expectLoading("正在加载测试计划");
});

it("announces candidate cases while creating a plan", async () => {
  server.use(
    http.get("/api/v1/tags", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
    http.get("/api/v1/cases/modules", () =>
      HttpResponse.json({ items: [] })),
    http.get("/api/v1/cases", pendingJson),
  );
  renderApp("/test-plans/new");
  await expectLoading("正在加载候选用例");
});

it("announces the test plan detail loading state", async () => {
  server.use(
    http.get("/api/v1/test-plans/plan_1", pendingJson),
    http.get("/api/v1/test-plans/plan_1/cases", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 10 })),
    http.get("/api/v1/test-plans/plan_1/executions", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 10 })),
  );
  renderApp("/test-plans/plan_1");
  await expectLoading("正在加载测试计划详情");
});

it("announces inline test plan detail loading states", async () => {
  server.use(
    http.get("/api/v1/test-plans/plan_1", () => HttpResponse.json(plan)),
    http.get("/api/v1/test-plans/plan_1/cases", pendingJson),
    http.get("/api/v1/test-plans/plan_1/executions", pendingJson),
  );
  renderApp("/test-plans/plan_1");
  await screen.findByRole("heading", { name: "核心回归" });
  await expectLoading("正在加载最近执行摘要");
  await expectLoading("正在加载执行记录");
  await expectLoading("正在加载绑定用例");
});

it("announces the plan run loading state", async () => {
  server.use(http.get("/api/v1/test-plans/plan_1", pendingJson));
  renderApp("/test-plans/plan_1/run");
  await expectLoading("正在加载运行配置");
});

it("announces the task report list loading state", async () => {
  server.use(
    http.get("/api/v1/test-plans", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 })),
    http.get("/api/v1/task-reports", pendingJson),
    http.get("/api/v1/task-reports/stats", () =>
      HttpResponse.json({
        report_count: 0,
        success_count: 0,
        failure_count: 0,
        average_pass_rate: 0,
      })),
  );
  renderApp("/task-reports");
  await expectLoading("正在加载测试报告");
});

it("announces the task report detail loading state", async () => {
  server.use(
    http.get("/api/v1/task-reports/execution_1", pendingJson),
  );
  renderApp("/task-reports/execution_1");
  await expectLoading("正在加载测试报告");
});
