import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  cancelTask,
  createCaseAndTask,
  getTask as getCurrentTask,
} from "./current-ui-helpers";

const ACCESS_KEY_ID = "AKLT00000000WXYZ";
const SECRET_ACCESS_KEY = "e2e-secret-value";
const SYSTEM_PROMPT_MARKER = "你是移动端 UI 自动化测试 Agent";
const SCREENSHOT_DIR = join("test-results", "loop4-mobile-use");
const TERMINAL_EVENTS = new Set([
  "task_finished",
  "runner_interrupted",
  "task_cancelled",
]);

type TestServer = {
  process: ChildProcess;
  output: string[];
};

type Task = {
  id: string;
  runner_type: string;
  execution_status: string;
  verdict: string | null;
  failure_type: string | null;
};

type TaskEvent = {
  sequence: number;
  type: string;
  payload: Record<string, unknown>;
};

type FailedRequest = {
  errorText: string;
  method: string;
  url: string;
  isNavigationRequest: boolean;
  resourceType: string;
};

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

async function startMobileUseServer(
  temporaryDataDir: string,
  port: number,
): Promise<TestServer> {
  const output: string[] = [];
  const child = spawn(
    "uv",
    [
      "run",
      "uvicorn",
      "mobile_use_server:app",
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
        APP_SECRET_KEY: "e2e-mobile-use-secret-key-at-least-32-bytes",
        APP_DATA_DIR: temporaryDataDir,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stdout?.on("data", (chunk) => output.push(String(chunk)));
  child.stderr?.on("data", (chunk) => output.push(String(chunk)));

  const readyUrl = `http://127.0.0.1:${port}/health/ready`;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Mobile Use server exited early:\n${output.join("")}`);
    }
    try {
      const response = await fetch(readyUrl);
      if (response.ok) {
        return { process: child, output };
      }
    } catch {
      // The child has not bound the port yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  await stopMobileUseServer({ process: child, output });
  throw new Error(`Mobile Use server did not become ready:\n${output.join("")}`);
}

async function stopMobileUseServer(testServer: TestServer): Promise<void> {
  const pid = testServer.process.pid;
  if (pid && testServer.process.exitCode === null) {
    process.kill(-pid, "SIGKILL");
    await once(testServer.process, "exit");
  }
}

async function initializeAdmin(page: Page, appUrl: string): Promise<void> {
  await page.goto(appUrl);
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("StrongPassword123!");
  await page.getByRole("button", { name: "创建管理员" }).click();
  await expect(page.getByRole("heading", { name: "任务列表" })).toBeVisible();
}

async function configureMobileUse(page: Page): Promise<void> {
  await page.getByRole("link", { name: "设置", exact: true }).click();
  await page.getByLabel("Access Key ID").fill(ACCESS_KEY_ID);
  await page.getByLabel("Secret Access Key").fill(SECRET_ACCESS_KEY);
  await page.getByLabel("Product ID").fill("product-e2e");
  await page.getByLabel("TOS Bucket").fill("mua-e2e");
  await page.getByLabel("TOS Region").fill("cn-beijing");
  await page.getByRole("button", { name: "保存所有更改" }).click();
  await expect(page.getByText("设置已保存。")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Access Key ID")).toHaveValue("");
  await expect(page.getByLabel("Secret Access Key")).toHaveValue("");
  await expect(page.getByText(/已配置：AKLT.*WXYZ/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "重新诊断" }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "刷新与查看 Pod 池" }).click();
  await expect(page).toHaveURL(/\/pods$/);
  const podRow = page.getByRole("row").filter({ hasText: "pod-e2e" });
  await expect(podRow).toContainText("运行中");
  await expect(podRow).toContainText("空闲");
  await expect(
    page.getByRole("button", { name: /删除|重启|关机/ }),
  ).toHaveCount(0);
}

async function createTask(page: Page, appUrl: string, title: string): Promise<string> {
  const task = await createCaseAndTask(page, {
    appUrl,
    title,
    content: `## 执行任务\n- 打开 demo_app 并验证首页\n\n## 用例通过标准\n- 页面出现首页`,
  });
  return task.id;
}

async function waitForTaskDetailResponses(
  page: Page,
  taskId: string,
  action: () => Promise<unknown>,
): Promise<void> {
  const taskPath = `/api/v1/tasks/${taskId}`;
  const [taskResponse, runtimeResponse] = await Promise.all([
    page.waitForResponse((response) =>
      response.request().method() === "GET"
      && new URL(response.url()).pathname === taskPath),
    page.waitForResponse((response) =>
      response.request().method() === "GET"
      && new URL(response.url()).pathname === `${taskPath}/runtime`),
    action(),
  ]);
  expect(taskResponse.ok()).toBe(true);
  expect(runtimeResponse.ok()).toBe(true);
}

async function gotoTaskDetail(
  page: Page,
  appUrl: string,
  taskId: string,
): Promise<void> {
  await waitForTaskDetailResponses(
    page,
    taskId,
    () => page.goto(`${appUrl}/tasks/${taskId}`),
  );
}

async function reloadTaskDetail(page: Page, taskId: string): Promise<void> {
  await waitForTaskDetailResponses(page, taskId, () => page.reload());
}

async function getTask(page: Page, taskId: string): Promise<Task> {
  return page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/tasks/${id}`);
    return response.json();
  }, taskId);
}

async function getEvents(page: Page, taskId: string): Promise<TaskEvent[]> {
  return page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/tasks/${id}/events`);
    return (await response.json()).items;
  }, taskId);
}

function expectStableEvents(events: TaskEvent[]): void {
  expect(events.map((event) => event.sequence)).toEqual(
    events.map((_event, index) => index + 1),
  );
  expect(events.filter((event) => TERMINAL_EVENTS.has(event.type))).toHaveLength(1);
}

async function runCompleteMobileUseFlow(
  page: Page,
  appUrl: string,
  server: TestServer,
  viewportName: string,
): Promise<void> {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: FailedRequest[] = [];
  const successfulResponses = new Set<string>();
  const responseBodies: string[] = [];
  const responseReads: Promise<void>[] = [];
  const renderedPages: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    failedRequests.push({
      errorText: request.failure()?.errorText ?? "unknown",
      method: request.method(),
      url: request.url(),
      isNavigationRequest: request.isNavigationRequest(),
      resourceType: request.resourceType(),
    });
  });
  page.on("response", (response) => {
    if (response.ok()) successfulResponses.add(response.url());
    if (!response.url().includes("/api/") && !response.url().includes("/health/")) {
      return;
    }
    responseReads.push(
      response
        .text()
        .then((body) => {
          responseBodies.push(body);
        })
        .catch(() => undefined),
    );
  });

  async function recordPage(stage: string): Promise<void> {
    renderedPages.push(`${stage}\n${await page.locator("body").innerText()}`);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      `${stage} 不应横向溢出`,
    ).toBe(true);
  }

  await initializeAdmin(page, appUrl);
  await configureMobileUse(page);
  await recordPage("设置");

  const passed = await createTask(page, appUrl, "Mobile通过");
  await expect.poll(
    async () => (await getCurrentTask(page, appUrl, passed)).execution_status,
    { timeout: 10_000 },
  ).toBe("result_ready");
  await gotoTaskDetail(page, appUrl, passed);
  await expect(page.getByText("成功", { exact: true }).first()).toBeVisible();
  await recordPage("pass 任务详情");

  const invalid = await createTask(page, appUrl, "Mobile结构非法");
  await expect.poll(
    async () => (await getCurrentTask(page, appUrl, invalid)).execution_status,
    { timeout: 10_000 },
  ).toBe("result_ready");
  await gotoTaskDetail(page, appUrl, invalid);
  await expect(page.getByText("失败", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("失败类型", { exact: true }).locator(".."),
  ).toContainText("evidence_missing");
  await expect(page.getByText("成功", { exact: true })).toHaveCount(0);
  await recordPage("invalid 任务详情");

  const cancelled = await createTask(page, appUrl, "Mobile取消");
  await expect.poll(
    async () => (await getCurrentTask(page, appUrl, cancelled)).execution_status,
    { timeout: 10_000 },
  ).toBe("running");
  await cancelTask(page, appUrl, cancelled);
  await expect.poll(
    async () => (await getCurrentTask(page, appUrl, cancelled)).execution_status,
    { timeout: 10_000 },
  ).toBe("cancelled");
  await gotoTaskDetail(page, appUrl, cancelled);
  await expect(page.getByText("已取消", { exact: true })).toBeVisible();
  await recordPage("cancel 详情");

  for (const taskId of [passed, invalid, cancelled]) {
    await gotoTaskDetail(page, appUrl, taskId);
    const task = await getTask(page, taskId);
    expect(task.runner_type).toBe("mobile_use");
    expectStableEvents(await getEvents(page, taskId));
  }
  expect(await getTask(page, passed)).toMatchObject({
    execution_status: "result_ready",
    verdict: "pass",
  });
  expect(await getTask(page, invalid)).toMatchObject({
    execution_status: "result_ready",
    verdict: "fail",
    failure_type: "evidence_missing",
  });

  await gotoTaskDetail(page, appUrl, invalid);
  await expect(page.getByText("失败", { exact: true }).first()).toBeVisible();
  await reloadTaskDetail(page, invalid);
  await expect(page.getByText("失败", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("失败类型", { exact: true }).locator(".."),
  ).toContainText("evidence_missing");
  expectStableEvents(await getEvents(page, invalid));
  await recordPage("invalid 刷新恢复");

  await mkdir(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    fullPage: true,
    path: join(SCREENSHOT_DIR, `${viewportName}-invalid-review.png`),
  });

  await page.goto(`${appUrl}/tasks/${passed}/report`);
  await expect(page.getByText("执行成功", { exact: true })).toBeVisible();
  await expect(page.getByText("首页已打开", { exact: true })).toBeVisible();
  await expect(page.getByText("截图显示首页标题", { exact: true })).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: join(SCREENSHOT_DIR, `${viewportName}-pass-report.png`),
  });
  await recordPage("pass 报告刷新");

  await Promise.all(responseReads);
  const observableOutput = [
    ...renderedPages,
    ...responseBodies,
    ...server.output,
  ].join("\n");
  for (const secret of [
    ACCESS_KEY_ID,
    SECRET_ACCESS_KEY,
    SYSTEM_PROMPT_MARKER,
    "StructOutput",
  ]) {
    expect(observableOutput).not.toContain(secret);
  }
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(
    failedRequests.filter((failure) => {
      const isSuccessfulNavigationAbort = (
        failure.errorText === "net::ERR_ABORTED"
        && failure.method === "GET"
        && failure.isNavigationRequest
        && failure.resourceType === "document"
        && successfulResponses.has(failure.url)
      );
      return !isSuccessfulNavigationAbort;
    }),
  ).toEqual([]);
}

for (const viewport of [
  { name: "desktop-1440x900", width: 1440, height: 900 },
  { name: "mobile-390x844", width: 390, height: 844 },
]) {
  test(`admin completes Mobile Use flow at ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    const dataDir = await mkdtemp(join(tmpdir(), `mua-loop4-${viewport.name}-`));
    const port = await findFreePort();
    const appUrl = `http://127.0.0.1:${port}`;
    let server: TestServer | undefined;

    try {
      server = await startMobileUseServer(dataDir, port);
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await runCompleteMobileUseFlow(page, appUrl, server, viewport.name);
    } finally {
      if (server) {
        await stopMobileUseServer(server);
      }
      await rm(dataDir, { recursive: true, force: true });
    }
  });
}
