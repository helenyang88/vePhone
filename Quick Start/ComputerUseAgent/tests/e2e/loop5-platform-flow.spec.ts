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
  getTask,
} from "./current-ui-helpers";

const ACCESS_KEY_ID = "AKLTLOOP50000SAFE";
const SECRET_ACCESS_KEY = "loop5-e2e-secret";
const PRODUCT_ID = "product-loop5";
const SCREENSHOT_DIR = join("test-results", "loop5-platform");
const SENSITIVE_MARKERS = [
  ACCESS_KEY_ID,
  SECRET_ACCESS_KEY,
];

type TestServer = {
  process: ChildProcess;
  output: string[];
};

type TaskResponse = {
  id: string;
  execution_status: string;
  verdict: string | null;
  failure_type: string | null;
};

type TraceSpan = {
  kind: string;
  name: string;
  status: string;
  request_id: string | null;
  error_code: string | null;
  attributes: Record<string, string | number | boolean | null>;
};

type TraceResponse = {
  spans: TraceSpan[];
};

type PodPoolItem = {
  pod_id: string;
  local_state: string;
  task_id: string | null;
};

type PodPoolResponse = {
  items: PodPoolItem[];
};

type FailedRequest = {
  errorText: string;
  method: string;
  url: string;
  isNavigationRequest: boolean;
  resourceType: string;
};

type RuntimeFailures = {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: FailedRequest[];
  successfulResponses: Set<string>;
  responseBodies: string[];
  responseReads: Promise<void>[];
};

type RenderedPageSnapshot = {
  stage: string;
  bodyText: string;
  inputValues: string[];
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

async function startServer(dataDir: string, port: number): Promise<TestServer> {
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
        APP_SECRET_KEY: "loop5-e2e-app-secret-key-at-least-32-bytes",
        APP_DATA_DIR: dataDir,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stdout?.on("data", (chunk) => output.push(String(chunk)));
  child.stderr?.on("data", (chunk) => output.push(String(chunk)));

  const readyUrl = `http://127.0.0.1:${port}/health/ready`;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Loop 5 server exited early:\n${output.join("")}`);
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
  await stopServer({ process: child, output });
  throw new Error(`Loop 5 server did not become ready:\n${output.join("")}`);
}

async function stopServer(server: TestServer): Promise<void> {
  const pid = server.process.pid;
  if (pid && server.process.exitCode === null) {
    process.kill(-pid, "SIGKILL");
    await once(server.process, "exit");
  }
}

function collectRuntimeFailures(page: Page): RuntimeFailures {
  const failures: RuntimeFailures = {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    successfulResponses: new Set<string>(),
    responseBodies: [],
    responseReads: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error") {
      failures.consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => failures.pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    failures.failedRequests.push({
      errorText: request.failure()?.errorText ?? "unknown",
      method: request.method(),
      url: request.url(),
      isNavigationRequest: request.isNavigationRequest(),
      resourceType: request.resourceType(),
    });
  });
  page.on("response", (response) => {
    if (response.ok()) failures.successfulResponses.add(response.url());
    if (!response.url().includes("/api/") && !response.url().includes("/health/")) {
      return;
    }
    failures.responseReads.push(
      response
        .text()
        .then((body) => {
          failures.responseBodies.push(body);
        })
        .catch(() => undefined),
    );
  });
  return failures;
}

async function expectNoHorizontalOverflow(page: Page, stage: string): Promise<void> {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    `${stage} 不应横向溢出`,
  ).toBe(true);
}

async function scanRenderedPage(
  page: Page,
  stage: string,
  snapshots: RenderedPageSnapshot[],
): Promise<void> {
  const snapshot = await page.evaluate((snapshotStage) => ({
    stage: snapshotStage,
    bodyText: document.body.innerText,
    inputValues: Array.from(document.querySelectorAll("input")).map(
      (input) => input.value,
    ),
  }), stage);
  snapshots.push(snapshot);

  const matches = SENSITIVE_MARKERS.flatMap((marker) => {
    const locations: string[] = [];
    if (snapshot.bodyText.includes(marker)) {
      locations.push("body.innerText");
    }
    snapshot.inputValues.forEach((value, index) => {
      if (value.includes(marker)) {
        locations.push(`input[${index}].value`);
      }
    });
    return locations.map((location) => `${stage}: ${marker} in ${location}`);
  });
  expect(matches, `${stage} 不应渲染敏感数据`).toEqual([]);
}

async function initializeAdmin(page: Page, appUrl: string): Promise<void> {
  await page.goto(appUrl);
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("StrongPassword123!");
  await page.getByRole("button", { name: "创建管理员" }).click();
  await expect(page.getByRole("heading", { name: "任务列表" })).toBeVisible();
}

async function configureProduct(page: Page, server: TestServer): Promise<void> {
  await page.getByRole("link", { name: "设置", exact: true }).click();
  await page.getByLabel("Access Key ID").fill(ACCESS_KEY_ID);
  await page.getByLabel("Secret Access Key").fill(SECRET_ACCESS_KEY);
  await page.getByLabel("Product ID").fill(PRODUCT_ID);
  await page.getByLabel("TOS Bucket").fill("loop5-e2e");
  await page.getByLabel("TOS Region").fill("cn-beijing");
  const saveResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT"
      && response.url().endsWith("/api/v1/settings/runner"),
  );
  await page.getByRole("button", { name: "保存所有更改" }).click();
  const saveResponse = await saveResponsePromise;
  expect(
    saveResponse.status(),
    `${await saveResponse.text()}\n${server.output.join("")}`,
  ).toBe(200);
  await expect(page.getByText("设置已保存。")).toBeVisible();
}

async function refreshPodPool(page: Page): Promise<void> {
  await page.getByRole("link", { name: "刷新与查看 Pod 池" }).click();
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.getByText("pod-loop5-a", { exact: true })).toBeVisible();
  await expect(page.getByText("pod-loop5-b", { exact: true })).toBeVisible();
  await expect(page.getByText("pod-loop5-c", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /删除|重启|关机/ })).toHaveCount(0);
}

async function createTask(page: Page, appUrl: string, title: string): Promise<string> {
  const task = await createCaseAndTask(page, {
    appUrl,
    title,
    content: `## 执行任务\n- 打开 loop5_app 并验证首页\n\n## 用例通过标准\n- 页面出现首页`,
  });
  await waitForTaskDetailSettled(
    page,
    task.id,
    () => page.goto(`${appUrl}/tasks/${task.id}`),
  );
  return task.id;
}

async function waitForTaskDetailSettled(
  page: Page,
  taskId: string,
  navigate: () => Promise<unknown>,
): Promise<void> {
  const taskPath = `/api/v1/tasks/${taskId}`;
  const [taskResponse, runtimeResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname === taskPath
        && response.ok(),
    ),
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname === `${taskPath}/runtime`
        && response.ok(),
    ),
    navigate(),
  ]);
  expect(taskResponse.status()).toBe(200);
  expect(runtimeResponse.status()).toBe(200);
}

async function apiGet<T>(page: Page, path: string): Promise<T> {
  return page.evaluate(async (url) => {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`GET ${url} failed with ${response.status}`);
    }
    return response.json();
  }, path);
}

async function allocatedPod(page: Page, taskId: string): Promise<string> {
  let podId = "";
  await expect
    .poll(async () => {
      const trace = await apiGet<TraceResponse>(
        page,
        `/api/v1/tasks/${taskId}/trace?view=flat&include_attempts=true`,
      );
      const allocation = trace.spans.find(
        (span) =>
          span.name === "DetailPod" &&
          span.kind === "remote_call" &&
          typeof span.attributes.pod_id === "string",
      );
      podId = String(allocation?.attributes.pod_id ?? "");
      return podId;
    })
    .not.toBe("");
  return podId;
}

async function expectTerminalAndReleased(page: Page, taskId: string): Promise<void> {
  await expect
    .poll(
      async () => (await apiGet<TaskResponse>(page, `/api/v1/tasks/${taskId}`)).execution_status,
      { timeout: 20_000 },
    )
    .toBe("result_ready");
  await expect
    .poll(async () => {
      const pool = await apiGet<PodPoolResponse>(page, "/api/v1/pod-pool");
      return pool.items.some((pod) => pod.task_id === taskId || pod.local_state === "leased");
    })
    .toBe(false);
}

async function expectSafeTrace(page: Page, taskId: string): Promise<void> {
  const trace = await apiGet<TraceResponse>(
    page,
    `/api/v1/tasks/${taskId}/trace?view=flat&include_attempts=true`,
  );
  expect(trace.spans.some((span) => span.request_id?.startsWith("req-result-safe-"))).toBe(true);
  expect(
    trace.spans.some(
      (span) =>
        span.attributes.action === "ListAgentRunCurrentStep" &&
        span.attributes.attempt === 1 &&
        span.status === "error" &&
        span.error_code === "remote_unavailable",
    ),
  ).toBe(true);
  expect(
    trace.spans.some(
      (span) =>
        span.attributes.action === "ListAgentRunCurrentStep" &&
        span.attributes.attempt === 2 &&
        span.status === "ok",
    ),
  ).toBe(true);
}

function unexpectedFailures(failures: RuntimeFailures): FailedRequest[] {
  return failures.failedRequests.filter((failure) => {
    const isSuccessfulNavigationAbort = (
      failure.errorText === "net::ERR_ABORTED"
      && failure.method === "GET"
      && failure.isNavigationRequest
      && failure.resourceType === "document"
      && failures.successfulResponses.has(failure.url)
    );
    return !isSuccessfulNavigationAbort;
  });
}

async function runPlatformFlow(
  page: Page,
  appUrl: string,
  server: TestServer,
): Promise<void> {
  const primaryFailures = collectRuntimeFailures(page);
  const renderedPages: RenderedPageSnapshot[] = [];
  await initializeAdmin(page, appUrl);
  await configureProduct(page, server);
  await scanRenderedPage(page, "设置保存后", renderedPages);
  await refreshPodPool(page);
  await expectNoHorizontalOverflow(page, "Pod 池");
  await scanRenderedPage(page, "Pod 池", renderedPages);

  const firstTaskId = await createTask(page, appUrl, "Loop5并发任务一");
  await expect
    .poll(
      async () =>
        (await apiGet<TaskResponse>(page, `/api/v1/tasks/${firstTaskId}`))
          .execution_status,
    )
    .toBe("running");
  const secondPage = await page.context().newPage();
  const secondFailures = collectRuntimeFailures(secondPage);
  const secondTaskId = await createTask(secondPage, appUrl, "Loop5并发任务二");

  const [firstPodId, secondPodId] = await Promise.all([
    allocatedPod(page, firstTaskId),
    allocatedPod(secondPage, secondTaskId),
  ]);
  expect(firstPodId).not.toBe(secondPodId);

  await expectTerminalAndReleased(page, firstTaskId);
  await expectTerminalAndReleased(secondPage, secondTaskId);
  await expectSafeTrace(page, firstTaskId);
  await expectSafeTrace(secondPage, secondTaskId);
  await page.goto(`${appUrl}/tasks/${firstTaskId}/trace`);
  await expect(
    page.getByRole("heading", { name: "执行步骤详情" }),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page, "Trace");
  await scanRenderedPage(page, "Trace", renderedPages);
  await waitForTaskDetailSettled(
    secondPage,
    secondTaskId,
    () => secondPage.goto(`${appUrl}/tasks/${secondTaskId}`),
  );
  await expect(secondPage.getByText("成功", { exact: true }).first()).toBeVisible();
  await expectNoHorizontalOverflow(secondPage, "第二条任务详情");
  await scanRenderedPage(secondPage, "第二条任务详情", renderedPages);
  await secondPage.close();

  const invalidTaskId = await createTask(page, appUrl, "Loop5结构非法");
  await expect.poll(
    async () => (await getTask(page, appUrl, invalidTaskId)).execution_status,
    { timeout: 20_000 },
  ).toBe("result_ready");
  expect(await getTask(page, appUrl, invalidTaskId)).toMatchObject({
    verdict: "fail",
    failure_type: "evidence_missing",
  });
  await waitForTaskDetailSettled(
    page,
    invalidTaskId,
    () => page.reload(),
  );
  await expect(page.getByText("失败", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("失败类型", { exact: true }).locator(".."),
  ).toContainText("evidence_missing");
  await expectNoHorizontalOverflow(page, "结构非法任务详情");
  await scanRenderedPage(page, "结构非法任务详情", renderedPages);

  const cancelledTaskId = await createTask(page, appUrl, "Loop5取消");
  await expect.poll(
    async () => (await getTask(page, appUrl, cancelledTaskId)).execution_status,
    { timeout: 20_000 },
  ).toBe("running");
  await cancelTask(page, appUrl, cancelledTaskId);
  await expect.poll(
    async () => (await getTask(page, appUrl, cancelledTaskId)).execution_status,
    { timeout: 20_000 },
  ).toBe("cancelled");
  await waitForTaskDetailSettled(
    page,
    cancelledTaskId,
    () => page.reload(),
  );
  await expect(page.getByText("已取消", { exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page, "取消任务详情");
  await scanRenderedPage(page, "取消任务详情", renderedPages);

  await mkdir(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    fullPage: true,
    path: join(
      SCREENSHOT_DIR,
      `${page.viewportSize()?.width ?? 0}x${page.viewportSize()?.height ?? 0}-cancelled.png`,
    ),
  });

  expect(
    await apiGet<TaskResponse>(page, `/api/v1/tasks/${firstTaskId}`),
  ).toMatchObject({
    execution_status: "result_ready",
    verdict: "pass",
    failure_type: null,
  });
  expect(
    await apiGet<TaskResponse>(page, `/api/v1/tasks/${secondTaskId}`),
  ).toMatchObject({
    execution_status: "result_ready",
    verdict: "pass",
    failure_type: null,
  });
  expect(new Set([
    firstTaskId,
    secondTaskId,
    invalidTaskId,
    cancelledTaskId,
  ]).size).toBe(4);

  await page.goto(`${appUrl}/tasks/${firstTaskId}/report`);
  await expect(page.getByText("执行成功", { exact: true })).toBeVisible();
  await expect(page.getByText("首页已打开", { exact: true })).toBeVisible();
  await expect(page.getByText("截图显示首页标题", { exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page, "成功报告");
  await scanRenderedPage(page, "成功报告", renderedPages);
  await page.screenshot({
    fullPage: true,
    path: join(
      SCREENSHOT_DIR,
      `${page.viewportSize()?.width ?? 0}x${page.viewportSize()?.height ?? 0}-success-report.png`,
    ),
  });

  await Promise.all([
    ...primaryFailures.responseReads,
    ...secondFailures.responseReads,
  ]);
  const observableOutput = [
    ...renderedPages.flatMap((snapshot) => [
      snapshot.bodyText,
      ...snapshot.inputValues,
    ]),
    ...primaryFailures.responseBodies,
    ...secondFailures.responseBodies,
    ...server.output,
  ].join("\n");
  for (const secret of SENSITIVE_MARKERS) {
    expect(observableOutput).not.toContain(secret);
  }
  expect(primaryFailures.consoleErrors).toEqual([]);
  expect(primaryFailures.pageErrors).toEqual([]);
  expect(unexpectedFailures(primaryFailures)).toEqual([]);
  expect(secondFailures.consoleErrors).toEqual([]);
  expect(secondFailures.pageErrors).toEqual([]);
  expect(unexpectedFailures(secondFailures)).toEqual([]);
}

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`${viewport.name} completes the Loop 5 management loop`, async ({ page }) => {
    test.setTimeout(90_000);
    const dataDir = await mkdtemp(join(tmpdir(), `mua-loop5-${viewport.name}-`));
    const port = await findFreePort();
    const appUrl = `http://127.0.0.1:${port}`;
    let server: TestServer | undefined;

    try {
      server = await startServer(dataDir, port);
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await runPlatformFlow(page, appUrl, server);
    } finally {
      if (server) {
        await stopServer(server);
      }
      await rm(dataDir, { recursive: true, force: true });
    }
  });
}
