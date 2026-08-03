import {
  expect,
  test,
  type Locator,
  type Page,
} from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";

const DESKTOP_SCREENSHOT = "test-results/test-plan-report-desktop-1440x900.png";
const TABLET_SCREENSHOT = "test-results/test-plan-report-tablet-1024x768.png";
const MOBILE_SCREENSHOT = "test-results/test-plan-report-mobile-390x844.png";
const PLAN_SEARCH_SCREENSHOT = "test-results/test-plan-search-control.png";
const CANDIDATE_SEARCH_SCREENSHOT = "test-results/candidate-search-controls.png";
const REPORT_FILTER_SCREENSHOT = "test-results/task-report-filter-controls.png";

type CreatedCase = {
  id: string;
  title: string;
};

type ReportDetail = {
  report_status: string;
  pass_rate: number;
  pass_count: number;
  fail_count: number;
  exception_count: number;
  tasks_total: number;
  tasks: Array<{
    task_id: string;
    case_id: string;
    case_title: string;
    verdict: string | null;
    failure_type: string | null;
  }>;
};

type TestServer = {
  process: ChildProcess;
  output: string[];
};

let appUrl = "";
let dataDir = "";
let testServer: TestServer | undefined;

async function findFreePort(): Promise<number> {
  const probe = createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const address = probe.address();
  if (!address || typeof address === "string") {
    probe.close();
    throw new Error("failed to allocate an E2E server port");
  }
  const port = address.port;
  probe.close();
  await once(probe, "close");
  return port;
}

async function startTestServer(
  temporaryDataDir: string,
  port: number,
): Promise<TestServer> {
  const output: string[] = [];
  const child = spawn(
    "uv",
    [
      "run",
      "uvicorn",
      "test_plan_server:app",
      "--app-dir",
      "tests/e2e",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
    ],
    {
      cwd: process.cwd(),
      detached: true,
      env: {
        ...process.env,
        APP_ENV: "e2e",
        APP_SECRET_KEY: "e2e-test-plan-secret-key-at-least-32-bytes",
        APP_DATA_DIR: temporaryDataDir,
        E2E_RUNNER_HOLD_FILE: join(temporaryDataDir, "runner-hold"),
        MOBILE_USE_PRODUCT_ID: "product-test-plan",
        MOBILE_USE_TOS_BUCKET: "test-plan-bucket",
        MOBILE_USE_TOS_REGION: "cn-beijing",
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stdout?.on("data", (chunk) => output.push(String(chunk)));
  child.stderr?.on("data", (chunk) => output.push(String(chunk)));

  const readyUrl = `http://127.0.0.1:${port}/health/ready`;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`test plan server exited early:\n${output.join("")}`);
    }
    try {
      const response = await fetch(readyUrl);
      if (response.ok) return { process: child, output };
    } catch {
      // The server has not bound the port yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  await stopTestServer({ process: child, output });
  throw new Error(`test plan server did not become ready:\n${output.join("")}`);
}

async function stopTestServer(server: TestServer): Promise<void> {
  const pid = server.process.pid;
  if (pid && server.process.exitCode === null) {
    process.kill(-pid, "SIGKILL");
    await once(server.process, "exit");
  }
}

test.beforeAll(async () => {
  dataDir = await mkdtemp(join(tmpdir(), "mua-test-plan-e2e-"));
  const port = await findFreePort();
  appUrl = `http://127.0.0.1:${port}`;
  testServer = await startTestServer(dataDir, port);
});

test.afterAll(async () => {
  if (testServer) await stopTestServer(testServer);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
});

async function initializeAdmin(page: Page): Promise<void> {
  await page.goto(appUrl);
  if (await page.getByRole("heading", { name: "任务列表" }).isVisible()) return;
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("StrongPassword123!");
  const setup = page.getByRole("button", { name: "创建管理员" });
  if (await setup.isVisible()) {
    await setup.click();
  } else {
    await page.getByRole("button", { name: "登录", exact: true }).click();
  }
  await expect(page.getByRole("heading", { name: "任务列表" })).toBeVisible();
}

async function csrfToken(page: Page): Promise<string> {
  const cookie = (await page.context().cookies()).find(
    (item) => item.name === "csrf",
  );
  if (!cookie) throw new Error("csrf cookie not found");
  return cookie.value;
}

async function seedCase(
  page: Page,
  title: string,
  tags: string[],
): Promise<CreatedCase> {
  const response = await page.request.post(`${appUrl}/api/v1/cases`, {
    headers: { "X-CSRF-Token": await csrfToken(page) },
    data: {
      title,
      module: "E2E",
      content_markdown: `## 执行任务\n- ${title}`,
      tags,
      automation_level: "auto",
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

async function expectNoHorizontalOverflow(
  page: Page,
  stage: string,
): Promise<void> {
  const overflow = await page.evaluate(() => ({
    pageWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    elements: Array.from(document.querySelectorAll("*"))
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.right > window.innerWidth + 1 || rect.left < -1;
      })
      .slice(0, 12)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          className: element.className,
          text: element.textContent?.trim().slice(0, 80),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
        };
      }),
  }));
  expect(
    overflow.pageWidth <= overflow.viewportWidth,
    `${stage} 不应横向溢出：${JSON.stringify(overflow)}`,
  ).toBe(true);
}

async function expectPlanRowActionsInSingleLine(
  row: Locator,
): Promise<void> {
  const actions = [
    row.getByRole("link", { name: "执行" }),
    row.getByRole("link", { name: "编辑" }),
    row.getByRole("button", { name: "删除" }),
  ];
  const boxes = await Promise.all(actions.map((action) =>
    action.boundingBox()));
  expect(boxes.every((box) => box !== null)).toBe(true);
  const [executeBox, editBox, deleteBox] = boxes;
  if (!executeBox || !editBox || !deleteBox) {
    throw new Error("test plan row action geometry is unavailable");
  }
  for (const box of [editBox, deleteBox]) {
    expect(Math.abs(box.y - executeBox.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.height - executeBox.height)).toBeLessThanOrEqual(1);
  }
  expect(executeBox.x).toBeLessThan(editBox.x);
  expect(editBox.x).toBeLessThan(deleteBox.x);

  const layout = await row.locator(".test-plan-row-actions").evaluate(
    (element) => {
      const rect = element.getBoundingClientRect();
      return {
        flexWrap: getComputedStyle(element).flexWrap,
        height: Math.round(rect.height),
        scrollHeight: element.scrollHeight,
      };
    },
  );
  expect(layout.flexWrap).toBe("nowrap");
  expect(layout.scrollHeight).toBeLessThanOrEqual(layout.height + 1);
}

async function expectSearchControlGeometry(
  page: Page,
  selector: string,
  expectedWidth: number,
): Promise<void> {
  const geometry = await page.locator(selector).evaluate((element) => {
    const input = element.querySelector("input");
    const label = element.querySelector(".sr-only");
    const labelStyle = label ? getComputedStyle(label) : null;
    const rect = element.getBoundingClientRect();
    const inputRect = input?.getBoundingClientRect();
    const labelRect = label?.getBoundingClientRect();
    return {
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      inputWidth: Math.round(inputRect?.width ?? 0),
      labelWidth: Math.round(labelRect?.width ?? 0),
      labelPosition: labelStyle?.position,
      labelOverflow: labelStyle?.overflow,
    };
  });
  expect(geometry).toMatchObject({
    width: expectedWidth,
    height: 36,
    labelWidth: 1,
    labelPosition: "absolute",
    labelOverflow: "hidden",
  });
  expect(geometry.inputWidth).toBeGreaterThan(expectedWidth - 4);
}

async function expectReportFilterGeometry(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    plan: Math.round(
      document.querySelector(
        ".task-report-filter-field.plan-filter .single-select-trigger",
      )?.getBoundingClientRect().width ?? 0,
    ),
    status: Math.round(
      document.querySelector(
        ".task-report-filter-field.status-filter .single-select-trigger",
      )?.getBoundingClientRect().width ?? 0,
    ),
    time: Math.round(
      document.querySelector(
        ".task-report-filter-field.time-filter .single-select-trigger",
      )?.getBoundingClientRect().width ?? 0,
    ),
    overflow: getComputedStyle(
      document.querySelector(".task-report-filter-bar")!,
    ).overflow,
  }));
  expect(widths).toEqual({
    plan: 220,
    status: 132,
    time: 154,
    overflow: "visible",
  });

  await page.getByRole("combobox", { name: "报告状态筛选" }).click();
  const menu = page.locator(
    ".task-report-filter-field.status-filter .single-select-menu",
  );
  await expect(menu).toBeVisible();
  const [barBox, menuBox] = await Promise.all([
    page.locator(".task-report-filter-bar").boundingBox(),
    menu.boundingBox(),
  ]);
  expect(barBox).not.toBeNull();
  expect(menuBox).not.toBeNull();
  expect((menuBox?.y ?? 0) + (menuBox?.height ?? 0))
    .toBeGreaterThan((barBox?.y ?? 0) + (barBox?.height ?? 0));
  await page.keyboard.press("Escape");
}

async function expectPageSizeMenuInsideCard(page: Page): Promise<void> {
  const trigger = page.getByRole("combobox", { name: "每页条数" });
  await trigger.click();
  const menu = page.locator(".pagination-page-size .single-select-menu");
  await expect(menu).toBeVisible();
  const [cardBox, triggerBox, menuBox] = await Promise.all([
    trigger.locator(
      "xpath=ancestor::div[contains(@class,'table-card')][1]",
    ).boundingBox(),
    trigger.boundingBox(),
    menu.boundingBox(),
  ]);
  expect(cardBox).not.toBeNull();
  expect(triggerBox).not.toBeNull();
  expect(menuBox).not.toBeNull();
  expect(menuBox?.y ?? 0)
    .toBeGreaterThanOrEqual(
      (triggerBox?.y ?? 0) + (triggerBox?.height ?? 0) + 4,
    );
  expect(menuBox?.x ?? 0).toBeGreaterThanOrEqual(cardBox?.x ?? 0);
  expect((menuBox?.x ?? 0) + (menuBox?.width ?? 0))
    .toBeLessThanOrEqual((cardBox?.x ?? 0) + (cardBox?.width ?? 0) + 1);
  expect((menuBox?.y ?? 0) + (menuBox?.height ?? 0))
    .toBeLessThanOrEqual((cardBox?.y ?? 0) + (cardBox?.height ?? 0) + 1);
  await page.keyboard.press("Escape");
}

test("creates, edits, runs, reports and preserves deleted-plan history", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const successfulNoContent = new Set<string>();
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    failedRequests.push(
      `${request.failure()?.errorText ?? "unknown"} ${request.method()} ${request.url()}`,
    );
  });
  page.on("response", (response) => {
    if (response.status() === 204) {
      successfulNoContent.add(response.url());
    }
  });

  await initializeAdmin(page);
  const cases = [
    await seedCase(page, "success", ["核心链路", "P0"]),
    await seedCase(page, "assertion_failure", ["核心链路"]),
    await seedCase(page, "evidence_missing", ["P0"]),
  ];

  await page.goto(`${appUrl}/test-plans/new`);
  await expectSearchControlGeometry(page, ".plan-case-search", 260);
  await page.locator(".plan-editor-section").nth(1).screenshot({
    path: CANDIDATE_SEARCH_SCREENSHOT,
  });
  await page.getByLabel("测试计划名称").fill("核心回归 E2E");

  await page.getByRole("combobox", { name: "计划标签" }).click();
  await page.getByRole("option", { name: /P0/ }).click();
  await page.getByRole("option", { name: /核心链路/ }).click();
  await page.keyboard.press("Escape");

  for (const item of cases) {
    await page.getByRole("checkbox", { name: `选择 ${item.title}` }).check();
  }
  await page.getByRole("button", { name: "保存测试计划" }).click();
  await expect(page).toHaveURL(/\/test-plans$/);
  const planLink = page.getByRole("link", { name: "核心回归 E2E" });
  await expect(planLink).toBeVisible();
  const planRow = page.getByRole("row").filter({ has: planLink });
  await expect(planRow.getByRole("link", { name: "执行" })).toHaveAttribute(
    "href",
    /\/test-plans\/plan_[^/]+\/run$/,
  );
  await expect(planRow.getByRole("link", { name: "编辑" })).toBeVisible();
  await expect(planRow.getByRole("button", { name: "删除" })).toBeVisible();
  await expectSearchControlGeometry(page, ".test-plan-search", 270);
  await page.locator(".filter-card").first().screenshot({
    path: PLAN_SEARCH_SCREENSHOT,
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await expectPageSizeMenuInsideCard(page);
  await expectPlanRowActionsInSingleLine(planRow);
  await expectNoHorizontalOverflow(page, "测试计划列表桌面端 1440x900");
  await page.setViewportSize({ width: 1024, height: 768 });
  await expectPageSizeMenuInsideCard(page);
  await expectPlanRowActionsInSingleLine(planRow);
  await expectNoHorizontalOverflow(page, "测试计划列表平板端 1024x768");
  await page.setViewportSize({ width: 390, height: 844 });
  await expectPageSizeMenuInsideCard(page);
  await expectPlanRowActionsInSingleLine(planRow);
  await expectNoHorizontalOverflow(page, "测试计划列表移动端 390x844");
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.getByRole("link", { name: "核心回归 E2E" }).click();
  await expect(page.getByRole("heading", { name: /核心回归 E2E/ })).toBeVisible();
  await page.getByRole("link", { name: "编辑" }).click();
  await expect(page).toHaveURL(/\/edit$/);
  await page.getByRole("button", {
    name: `置顶 ${cases[2].id}`,
  }).click();
  await page.getByRole("button", { name: "保存测试计划" }).click();

  await expect(page).toHaveURL(/\/test-plans$/);
  await page.getByRole("link", { name: "核心回归 E2E" }).click();
  const planId = new URL(page.url()).pathname.split("/")[2];
  const boundCasesResponse = await page.request.get(
    `${appUrl}/api/v1/test-plans/${planId}/cases?page=1&page_size=10`,
  );
  expect(boundCasesResponse.status()).toBe(200);
  const boundCases = await boundCasesResponse.json() as {
    items: CreatedCase[];
  };
  expect(boundCases.items[0]?.id).toBe(cases[2].id);
  const boundCasesTable = page.getByRole("table", {
    name: "绑定测试用例",
  });
  await expect(boundCasesTable.locator("tbody tr").first())
    .toContainText("evidence_missing");
  const detailPageSize = page.getByRole("combobox", { name: "每页条数" });
  await detailPageSize.click();
  await page.getByRole("option", { name: "20 条 / 页" }).click();
  await expect(page).toHaveURL(/page_size=20/);
  await page.goBack();
  await expect(page).not.toHaveURL(/page_size=20/);

  await page.goto(`${appUrl}/test-plans`);
  const runLink = page.getByRole("link", { name: "核心回归 E2E" });
  const runRow = page.getByRole("row").filter({ has: runLink });
  await runRow.getByRole("link", { name: "执行" }).click();
  await expect(page).toHaveURL(/\/test-plans\/plan_[^/]+\/run$/);
  await expect(page.getByRole("heading", { name: "运行测试计划" })).toBeVisible();
  await page.getByRole("button", { name: "确认并开始执行" }).click();

  await expect(page).toHaveURL(/\/task-reports\/execution_/);
  await expect(page.getByRole("heading", { name: "核心回归 E2E" })).toBeVisible();
  const executionId = new URL(page.url()).pathname.split("/")[2];
  let terminalReport: ReportDetail | undefined;
  await expect.poll(async () => {
    const response = await page.request.get(
      `${appUrl}/api/v1/task-reports/${executionId}?page=1&page_size=10`,
    );
    expect(response.status()).toBe(200);
    terminalReport = await response.json() as ReportDetail;
    return terminalReport.report_status;
  }, {
    timeout: 20_000,
    intervals: [250, 500, 1000],
  }).toBe("exception");
  expect(terminalReport).toMatchObject({
    report_status: "exception",
    pass_count: 1,
    fail_count: 1,
    exception_count: 1,
    pass_rate: 33.33,
    tasks_total: 3,
  });
  expect(terminalReport?.tasks).toHaveLength(3);
  expect(terminalReport?.tasks.map((task) => task.case_title)).toEqual([
    "evidence_missing",
    "success",
    "assertion_failure",
  ]);

  await expect(page.getByTestId("plan-report-result").getByText("异常"))
    .toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("plan-report-rate")).toContainText("33.33%");
  await expect(page.getByTestId("plan-report-passed")).toContainText("1 / 3");
  const taskRows = page.getByRole("table").filter({
    has: page.getByRole("columnheader", { name: "任务 ID" }),
  }).locator("tbody tr");
  await expect(taskRows).toHaveCount(3);
  await expect(taskRows.nth(0)).toContainText("evidence_missing");
  await expect(taskRows.nth(0).locator("td").nth(4))
    .toHaveText("evidence_missing");
  await expect(taskRows.nth(1)).toContainText("success");
  await expect(taskRows.nth(1).locator("td").nth(3)).toHaveText("成功");
  await expect(taskRows.nth(2)).toContainText("assertion_failure");
  await expect(taskRows.nth(2).locator("td").nth(4))
    .toHaveText("assertion_failed");
  await expect(page.getByRole("link", { name: /^task_/ }).first()).toBeVisible();

  const reportUrl = page.url();
  await page.goto(`${appUrl}/task-reports`);
  await expect(page.getByRole("heading", { name: "任务报告" })).toBeVisible();
  await expectReportFilterGeometry(page);
  const planFilter = page.getByRole("combobox", { name: "测试计划筛选" });
  await planFilter.click();
  await expect(page.getByRole("searchbox", { name: "搜索测试计划" }))
    .toBeVisible();
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expectPageSizeMenuInsideCard(page);
  await page.setViewportSize({ width: 1024, height: 768 });
  await expectPageSizeMenuInsideCard(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectPageSizeMenuInsideCard(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const timeFilter = page.getByRole("combobox", { name: "时间筛选" });
  await timeFilter.click();
  await page.getByRole("option", { name: "最近一周" }).click();
  await expect(timeFilter).toContainText("最近一周");
  await expect(page).toHaveURL(/time_range=7d/);
  const globalReportCount = page.getByTestId("report-count");
  await expect(globalReportCount).toContainText("1");
  await page.getByRole("combobox", { name: "报告状态筛选" }).click();
  await page.getByRole("option", { name: "成功" }).click();
  await expect(page.getByText("无匹配结果，请调整搜索条件或表头筛选"))
    .toBeVisible();
  await expect(globalReportCount).toContainText("1");
  await page.getByRole("button", { name: "重置筛选" }).click();
  await page.locator(".task-report-filter-bar").screenshot({
    path: REPORT_FILTER_SCREENSHOT,
  });
  await page.goto(reportUrl);
  await expect(page.getByRole("heading", { name: "核心回归 E2E" })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expectNoHorizontalOverflow(page, "报告详情桌面端 1440x900");
  await page.screenshot({
    path: DESKTOP_SCREENSHOT,
  });
  await page.setViewportSize({ width: 1024, height: 768 });
  await expectNoHorizontalOverflow(page, "报告详情平板端 1024x768");
  await page.screenshot({
    path: TABLET_SCREENSHOT,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page, "报告详情移动端 390x844");
  await page.screenshot({
    path: MOBILE_SCREENSHOT,
  });

  await page.getByRole("link", { name: /^task_/ }).first().click();
  await expect(page).toHaveURL(/\/tasks\/task_/);
  await page.goBack();
  await expect(page).toHaveURL(/\/task-reports\/execution_/);

  await page.goto(`${appUrl}/test-plans`);
  const deleteLink = page.getByRole("link", { name: "核心回归 E2E" });
  const deleteRow = page.getByRole("row").filter({ has: deleteLink });
  const deleteButton = deleteRow.getByRole("button", { name: "删除" });
  await deleteButton.click();
  await expect(page.getByText(/历史报告不会删除/)).toBeVisible();
  await expect(page.locator(".app-shell")).toHaveAttribute("inert", "");
  await expect(page.getByRole("button", { name: "取消" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "确认删除" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".app-shell")).not.toHaveAttribute("inert");
  await expect(deleteButton).toBeFocused();

  await deleteButton.click();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(
    page.getByRole("heading", { name: "测试计划", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "核心回归 E2E" })).toHaveCount(0);

  await page.goto(reportUrl);
  await expect(page.getByRole("heading", { name: "核心回归 E2E" })).toBeVisible();
  await expect(page.getByTestId("plan-report-result").getByText("异常"))
    .toBeVisible();
  await expect(page.getByTestId("plan-report-rate")).toContainText("33.33%");
  await expect(page.getByTestId("plan-report-passed")).toContainText("1 / 3");
  const historicalResponse = await page.request.get(
    `${appUrl}/api/v1/task-reports/${executionId}?page=1&page_size=10`,
  );
  expect(historicalResponse.status()).toBe(200);
  expect(await historicalResponse.json()).toMatchObject({
    report_status: "exception",
    pass_count: 1,
    fail_count: 1,
    exception_count: 1,
    pass_rate: 33.33,
    tasks_total: 3,
  });
  await expect(page.getByRole("table").filter({
    has: page.getByRole("columnheader", { name: "任务 ID" }),
  }).locator("tbody tr")).toHaveCount(3);

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(
    failedRequests.filter((failure) => {
      if (!failure.startsWith("net::ERR_ABORTED DELETE ")) return true;
      const url = failure.slice("net::ERR_ABORTED DELETE ".length);
      return !successfulNoContent.has(url);
    }),
  ).toEqual([]);
});
