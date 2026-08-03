import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

import type { TestCase } from "../../web/api/types";
import { expectCsrf, renderApp, server, user } from "./setup";

const STYLES = readFileSync("web/styles.css", "utf8");

function savedCase(overrides: Partial<TestCase> = {}): TestCase {
  return {
    id: "case_saved",
    title: "新建链路",
    module: "登录",
    content_markdown: "## 执行任务\n打开首页",
    tags: [],
    automation_level: "auto",
    execution_count: 0,
    pass_count: 0,
    fail_count: 0,
    last_executed_at: null,
    created_by: "admin",
    created_at: "2026-07-28T03:00:00Z",
    updated_at: "2026-07-28T03:00:00Z",
    ...overrides,
  };
}

it("新建用例页不展示自动化等级并按默认自动执行保存", async () => {
  let submitted: unknown;
  server.use(
    http.get("/api/v1/cases/template", () =>
      HttpResponse.json({ template: "## 执行任务\n打开首页" })),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: [] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: [] })),
    http.post("/api/v1/cases", async ({ request }) => {
      expectCsrf(request);
      submitted = await request.json();
      return HttpResponse.json(savedCase(), { status: 201 });
    }),
    http.get("/api/v1/cases/case_saved", () => HttpResponse.json(savedCase())),
    http.get("/api/v1/cases/case_saved/tasks", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 5 })),
  );

  renderApp("/cases/new");

  expect(await screen.findByRole("heading", { name: "新建用例" })).toBeVisible();
  expect(screen.queryByText("自动化等级")).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "自动化等级" })).not.toBeInTheDocument();
  expect(screen.getByText("所属模块").closest(".case-metadata-row")).toBeInTheDocument();
  expect(STYLES).toMatch(
    /\.case-metadata-row\s*\{[^}]*margin-bottom:\s*1\.25rem;/s,
  );

  await user.type(
    screen.getByPlaceholderText("例如：打开抖音APP查看3个视频"),
    "新建链路",
  );
  await user.type(
    screen.getByPlaceholderText("例如：登录注册、首页、商品"),
    "登录",
  );
  await user.click(screen.getByRole("button", { name: "保存" }));

  await waitFor(() =>
    expect(submitted).toEqual(
      expect.objectContaining({
        title: "新建链路",
        module: "登录",
        automation_level: "auto",
      }),
    ),
  );
});
