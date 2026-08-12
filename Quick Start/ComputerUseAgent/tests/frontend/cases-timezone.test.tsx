import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import type { TestCaseListResponse } from "../../web/api/types";
import { renderApp, server } from "./setup";

const caseList: TestCaseListResponse = {
  total: 1,
  page: 1,
  page_size: 10,
  items: [
    {
      id: "case_timezone",
      title: "时区验证用例",
      module: "回归",
      content_markdown: "## 执行任务\n验证用例库时间展示",
      tags: ["P0"],
      automation_level: "auto",
      execution_count: 1,
      pass_count: 1,
      fail_count: 0,
      last_executed_at: "2026-07-28T03:30:00Z",
      created_by: "admin",
      created_at: "2026-07-28T03:00:00Z",
      updated_at: "2026-07-28T03:00:00Z",
    },
  ],
};

it("renders case list timestamps in UTC+8 with a stable absolute format", async () => {
  server.use(
    http.get("/api/v1/cases", () => HttpResponse.json(caseList)),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["回归"] })),
  );

  renderApp("/cases");

  expect(await screen.findByRole("link", { name: "时区验证用例" })).toBeVisible();
  expect(screen.getByText("2026-07-28 11:00:00")).toBeVisible();
  expect(screen.getByTitle("2026-07-28 11:30:00")).toBeVisible();
});

it("renders case editor statistics timestamps in UTC+8", async () => {
  server.use(
    http.get("/api/v1/cases/case_timezone", () => HttpResponse.json(caseList.items[0])),
    http.get("/api/v1/cases/case_timezone/tasks", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 5 })),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["回归"] })),
  );

  renderApp("/cases/case_timezone/edit");

  expect(await screen.findByText("执行统计")).toBeVisible();
  expect(screen.getByText("最近执行：2026-07-28 11:30:00")).toBeVisible();
  expect(screen.getByText("创建时间：2026-07-28 11:00:00")).toBeVisible();
  expect(screen.getByText("更新时间：2026-07-28 11:00:00")).toBeVisible();
});
