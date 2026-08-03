import { screen, waitFor, within } from "@testing-library/react";
import { delay, HttpResponse, http } from "msw";
import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";

import type { TestCase, TestCaseListResponse } from "../../web/api/types";
import { expectCsrf, renderApp, server, user } from "./setup";

const STYLES = readFileSync("web/styles.css", "utf8");

function makeCase(overrides: Partial<TestCase>): TestCase {
  return {
    id: "case_alpha",
    title: "示例用例",
    module: "登录",
    content_markdown: "## 执行任务\n打开",
    tags: ["P0", "smoke"],
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

function listOf(items: TestCase[]): TestCaseListResponse {
  return { total: items.length, page: 1, page_size: 10, items };
}

it("never derives case KPIs from a filtered list", async () => {
  server.use(
    http.get("/api/v1/cases/stats", async () => {
      await delay("infinite");
      return HttpResponse.json({});
    }),
    http.get("/api/v1/cases/tags", () =>
      HttpResponse.json({ items: [] })),
    http.get("/api/v1/cases/modules", () =>
      HttpResponse.json({ items: [] })),
    http.get("/api/v1/cases", ({ request }) => {
      const filtered = Boolean(
        new URL(request.url).searchParams.get("search"),
      );
      return HttpResponse.json({
        items: filtered ? [] : [makeCase({ id: "case_global" })],
        total: filtered ? 0 : 7,
        page: 1,
        page_size: 10,
      });
    }),
  );

  renderApp("/cases");
  await screen.findByRole("link", { name: "示例用例" });
  expect(screen.getByTestId("case-metric-total")).toHaveTextContent("0");
  await user.type(
    screen.getByRole("searchbox", { name: "搜索用例" }),
    "missing",
  );

  expect(await screen.findByText(
    "无匹配结果，请调整搜索条件或表头筛选",
  )).toBeVisible();
  expect(screen.getByTestId("case-metric-total")).toHaveTextContent("0");
  expect(screen.queryByRole("link", { name: "创建第一个用例" }))
    .not.toBeInTheDocument();
});

it("filters by clicking a tag in the case row and drops the automation column", async () => {
  const seenTags: string[] = [];
  const seenModules: string[] = [];
  server.use(
    http.get("/api/v1/cases/stats", () =>
      HttpResponse.json({
        total: 3,
        auto_count: 3,
        today_executions: 2,
        total_executions: 22,
        pass_rate: 73,
      })),
    http.get("/api/v1/cases", ({ request }) => {
      const url = new URL(request.url);
      const tag = url.searchParams.get("tag");
      const module = url.searchParams.get("module");
      seenTags.push(tag ?? "");
      seenModules.push(module ?? "");
      if (tag === "smoke") {
        return HttpResponse.json(listOf([makeCase({ id: "case_alpha", title: "示例用例" })]));
      }
      return HttpResponse.json(
        listOf([
          makeCase({ id: "case_alpha", title: "示例用例", tags: ["P0", "smoke"] }),
          makeCase({ id: "case_beta", title: "另一个用例", tags: ["P0"] }),
        ]),
      );
    }),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0", "smoke"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["登录"] })),
  );

  renderApp("/cases");

  await screen.findByRole("link", { name: "示例用例" });
  // The automation column header should be gone.
  expect(screen.queryByRole("columnheader", { name: "自动化" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
    "用例ID",
    "用例名称",
    "模块",
    "标签",
    "执行次数",
    "通过率",
    "最近执行",
    "创建人",
    "更新时间",
    "操作",
  ]);
  expect(screen.getByRole("table")).toHaveClass("task-table");
  expect(screen.getByText("第 1 / 1 页")).toBeVisible();
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  expect(screen.queryByRole("combobox", { name: "每页条数" })).not.toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "用例ID" }))
    .toHaveClass("case-sticky-header");
  expect(screen.getByTestId("case-metric-total").closest(".metric-grid"))
    .toHaveClass("case-metric-grid");
  expect(screen.queryByText("可自动化")).not.toBeInTheDocument();
  expect(screen.queryByText(/自动化率/)).not.toBeInTheDocument();
  expect(screen.getByTestId("case-metric-today")).toHaveTextContent("今日执行");
  expect(screen.getByTestId("case-metric-today")).toHaveTextContent("2");
  expect(screen.getByTestId("case-metric-today")).toHaveTextContent("中国时区今日");
  expect(document.querySelector(".cases-page .page-content"))
    .toHaveClass("case-content-compact");
  expect(document.querySelector(".case-action-message")).not.toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "操作" }))
    .toHaveClass("case-actions-cell");

  const row = screen.getByRole("link", { name: "示例用例" }).closest("tr") as HTMLElement;
  expect(within(row).getByRole("link", { name: "示例用例" }))
    .toHaveClass("case-name-link-neutral");
  expect(within(row).getByText("admin")).toHaveClass("case-owner-text");
  expect(within(row).getAllByRole("cell").at(-1)).toHaveClass("case-actions-cell");
  expect(within(row).getByLabelText("执行用例").closest(".row-actions"))
    .toHaveClass("case-row-actions");
  const p0Tag = within(row).getByRole("button", { name: "P0" });
  const smokeTag = within(row).getByRole("button", { name: "smoke" });
  expect(p0Tag.className).toMatch(/tag-tone-\d/);
  expect(smokeTag.className).toMatch(/tag-tone-\d/);
  expect(p0Tag.className).not.toBe(smokeTag.className);

  await user.click(screen.getByRole("combobox", { name: "模块筛选" }));
  await user.click(screen.getByRole("option", { name: "登录" }));
  await waitFor(() => expect(seenModules).toContain("登录"));

  // Click the "smoke" tag button inside the first row.
  const filteredRow = screen.getByRole("link", { name: "示例用例" }).closest("tr") as HTMLElement;
  await user.click(within(filteredRow).getByRole("button", { name: "smoke" }));

  await waitFor(() => expect(seenTags).toContain("smoke"));
});

it("keeps long case names compact while exposing the full name on hover and focus", async () => {
  const longTitle = "完整链路验证-这是一个非常长的用例名称用于验证悬浮时可以查看完整标题且不挤压模块列";
  server.use(
    http.get("/api/v1/cases/stats", () =>
      HttpResponse.json({
        total: 1,
        auto_count: 1,
        today_executions: 0,
        total_executions: 0,
        pass_rate: 0,
      })),
    http.get("/api/v1/cases", () =>
      HttpResponse.json(listOf([makeCase({ id: "case_long_name", title: longTitle, module: "E2E" })]))),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["E2E"] })),
  );

  renderApp("/cases");

  const link = await screen.findByRole("link", { name: longTitle });
  const wrapper = link.closest(".case-name-wrapper") as HTMLElement;
  expect(wrapper).toHaveAttribute("data-full-title", longTitle);
  expect(link).not.toHaveAttribute("title");
  expect(STYLES).toMatch(
    /\.case-name-wrapper\s*\{[^}]*max-width:\s*280px;[^}]*position:\s*relative/s,
  );
  expect(STYLES).toMatch(
    /\.case-name-wrapper::after\s*\{[^}]*content:\s*attr\(data-full-title\)/s,
  );
  expect(STYLES).toMatch(
    /\.case-name-wrapper::after\s*\{[^}]*bottom:\s*calc\(100% \+ 6px\)/s,
  );
  expect(STYLES).not.toMatch(
    /\.case-name-wrapper::after\s*\{[^}]*top:\s*calc\(100% \+ 6px\)/s,
  );
  expect(STYLES).toMatch(
    /\.case-name-wrapper::after\s*\{[^}]*background:\s*var\(--mua-card\);[^}]*color:\s*var\(--mua-neutral-800\)/s,
  );
  expect(STYLES).not.toMatch(
    /\.case-name-wrapper::after\s*\{[^}]*background:\s*var\(--mua-neutral-900\)/s,
  );
  expect(STYLES).toMatch(
    /\.case-name-wrapper:hover::after,[\s\S]*?\.case-name-wrapper:focus-within::after\s*\{[^}]*opacity:\s*1/s,
  );
  expect(STYLES).toMatch(
    /\.case-name-link\s*\{[^}]*max-width:\s*280px;[^}]*overflow:\s*hidden;[^}]*text-overflow:\s*ellipsis/s,
  );
});

it("uses task-list style live search and removes automation level filtering", async () => {
  const seenQueries: string[] = [];
  server.use(
    http.get("/api/v1/cases", ({ request }) => {
      seenQueries.push(new URL(request.url).search);
      return HttpResponse.json(listOf([makeCase({ id: "case_prefix", title: "打开抖音 APP" })]));
    }),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0", "smoke"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["登录"] })),
  );

  renderApp("/cases");

  const search = await screen.findByLabelText("搜索用例");
  expect(search.closest(".case-filter-search")).toHaveClass("task-search");
  expect(STYLES).toMatch(
    /\.case-filter-search\s*\{[^}]*flex:\s*0 1 280px;[^}]*max-width:\s*280px;[^}]*min-width:\s*260px;/s,
  );
  expect(screen.getByRole("combobox", { name: "标签筛选" }).closest(".single-select"))
    .not.toHaveClass("case-tag-filter");
  expect(STYLES).not.toMatch(/\.case-tag-filter \.single-select-menu/);
  expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "清空搜索" })).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "自动化等级筛选" })).not.toBeInTheDocument();

  await user.type(search, "打开抖音");

  await waitFor(() =>
    expect(seenQueries.some((query) =>
      query.includes("search=%E6%89%93%E5%BC%80%E6%8A%96%E9%9F%B3"),
    )).toBe(true),
  );
});

it("copies the full case id via the copy button", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });

  server.use(
    http.get("/api/v1/cases", () => HttpResponse.json(listOf([makeCase({ id: "case_copy_me" })]))),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["登录"] })),
  );

  renderApp("/cases");

  // Full id shown (not truncated placeholder).
  expect(await screen.findByText("case_copy_me")).toBeVisible();

  const row = screen.getByText("case_copy_me").closest("tr") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "复制用例ID" }));

  await waitFor(() => expect(writeText).toHaveBeenCalledWith("case_copy_me"));
});

it("shows execution count and pass rate in separate columns", async () => {
  server.use(
    http.get("/api/v1/cases", () =>
      HttpResponse.json(listOf([
        makeCase({
          id: "case_rate",
          execution_count: 4,
          pass_count: 3,
          fail_count: 1,
        }),
      ])),
    ),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["登录"] })),
  );

  renderApp("/cases");

  const row = (await screen.findByText("case_rate")).closest("tr") as HTMLElement;
  const cells = within(row).getAllByRole("cell");
  expect(cells[4]).toHaveTextContent("4");
  expect(cells[5]).toHaveTextContent("75%");
});

it("copies a case and refreshes the list", async () => {
  let items = [makeCase({ id: "case_source", title: "登录核心链路" })];
  server.use(
    http.get("/api/v1/cases", () => HttpResponse.json(listOf(items))),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["登录"] })),
    http.post("/api/v1/cases/case_source/copy", ({ request }) => {
      expectCsrf(request);
      const copied = makeCase({
        ...items[0],
        id: "case_copy",
        title: "登录核心链路 副本",
      });
      items = [items[0], copied];
      return HttpResponse.json(copied, { status: 201 });
    }),
  );

  renderApp("/cases");

  const row = (await screen.findByText("case_source")).closest("tr") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "复制用例" }));

  expect(await screen.findByRole("link", { name: "登录核心链路 副本" })).toBeVisible();
});

it("confirms deletion before removing a case", async () => {
  let items = [makeCase({ id: "case_delete", title: "待删除用例" })];
  let deleteRequests = 0;
  server.use(
    http.get("/api/v1/cases", () => HttpResponse.json(listOf(items))),
    http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
    http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: ["登录"] })),
    http.delete("/api/v1/cases/case_delete", ({ request }) => {
      expectCsrf(request);
      deleteRequests += 1;
      items = [];
      return new HttpResponse(null, { status: 204 });
    }),
  );

  renderApp("/cases");

  const row = (await screen.findByText("case_delete")).closest("tr") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "删除用例" }));
  expect(screen.getByRole("dialog", { name: "删除用例" })).toBeVisible();
  expect(deleteRequests).toBe(0);

  await user.click(screen.getByRole("button", { name: "确认删除" }));

  await waitFor(() => expect(deleteRequests).toBe(1));
  await waitFor(() => expect(screen.queryByText("case_delete")).not.toBeInTheDocument());
});

it("restores case filters and pagination from the URL", async () => {
  const seenQueries: string[] = [];
  server.use(
    http.get("/api/v1/cases", ({ request }) => {
      seenQueries.push(new URL(request.url).search);
      return HttpResponse.json({
        items: [makeCase({ id: "case_deep_link" })],
        total: 11,
        page: 2,
        page_size: 10,
      });
    }),
    http.get("/api/v1/cases/tags", () =>
      HttpResponse.json({ items: ["smoke"] })),
    http.get("/api/v1/cases/modules", () =>
      HttpResponse.json({ items: ["登录"] })),
  );

  renderApp("/cases?page=2&search=示例&module=登录&tag=smoke");

  expect(await screen.findByText("case_deep_link")).toBeVisible();
  expect(screen.getByLabelText("搜索用例")).toHaveValue("示例");
  expect(screen.getByRole("combobox", { name: "模块筛选" })).toHaveTextContent("登录");
  expect(screen.getByRole("combobox", { name: "标签筛选" })).toHaveTextContent("smoke");
  expect(screen.queryByRole("combobox", { name: "自动化等级筛选" })).not.toBeInTheDocument();
  expect(screen.getByText("第 2 / 2 页")).toBeVisible();
  expect(seenQueries.some((query) =>
    query.includes("page=2")
    && query.includes("search=%E7%A4%BA%E4%BE%8B")
    && query.includes("module=%E7%99%BB%E5%BD%95")
    && query.includes("tag=smoke"),
  )).toBe(true);
  expect(seenQueries.every((query) => !query.includes("automation_level"))).toBe(true);
});
