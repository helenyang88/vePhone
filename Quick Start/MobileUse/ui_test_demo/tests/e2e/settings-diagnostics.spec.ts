import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";

const ACCESS_KEY_ID = "AKLT-LOOP3-ORIGINAL-7890";
const SECRET_ACCESS_KEY = "loop3-secret-access-key-never-leak";
const ARK_API_KEY = "loop3-ark-api-key-never-leak";
const SCREENSHOT_DIR = join("test-results", "loop3-settings-diagnostics");

type TestServer = {
  process: ChildProcess;
  output: string[];
};

let appUrl: string;
let dataDir: string;
let notReadyFile: string;
let server: TestServer;

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

async function startDiagnosticsServer(
  temporaryDataDir: string,
  port: number,
): Promise<TestServer> {
  const output: string[] = [];
  const child = spawn(
    "uv",
    [
      "run",
      "uvicorn",
      "diagnostics_server:app",
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
        APP_SECRET_KEY: "e2e-diagnostics-secret-key-at-least-32-bytes",
        APP_DATA_DIR: temporaryDataDir,
        E2E_NOT_READY_FILE: join(temporaryDataDir, "not-ready"),
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stdout?.on("data", (chunk) => output.push(String(chunk)));
  child.stderr?.on("data", (chunk) => output.push(String(chunk)));

  const readyUrl = `http://127.0.0.1:${port}/health/ready`;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`diagnostics server exited early:\n${output.join("")}`);
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
  await stopDiagnosticsServer({ process: child, output });
  throw new Error(`diagnostics server did not become ready:\n${output.join("")}`);
}

async function stopDiagnosticsServer(testServer: TestServer): Promise<void> {
  const pid = testServer.process.pid;
  if (pid && testServer.process.exitCode === null) {
    process.kill(-pid, "SIGKILL");
    await once(testServer.process, "exit");
  }
}

async function expectPageSecretsAbsent(page: Page, stage: string): Promise<void> {
  const pageText = await page.locator("body").innerText();
  const inputValues = await page.locator("input").evaluateAll((inputs) =>
    inputs.map((input) => (input as HTMLInputElement).value),
  );
  const pageState = [pageText, ...inputValues].join("\n");
  for (const secret of [ACCESS_KEY_ID, SECRET_ACCESS_KEY, ARK_API_KEY]) {
    expect(pageState, `${stage} 页面不得包含测试秘密`).not.toContain(secret);
  }
}

test.beforeAll(async () => {
  dataDir = await mkdtemp(join(tmpdir(), "mua-loop3-e2e-"));
  const port = await findFreePort();
  appUrl = `http://127.0.0.1:${port}`;
  notReadyFile = join(dataDir, "not-ready");
  server = await startDiagnosticsServer(dataDir, port);
});

test.afterAll(async () => {
  if (server) {
    await stopDiagnosticsServer(server);
  }
  if (dataDir) {
    await rm(dataDir, { recursive: true, force: true });
  }
});

test("admin configures settings and uses the Mobile Use Pod pool safely", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const responseBodies: string[] = [];
  const responseReads: Promise<void>[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.method()} ${request.url()}`);
  });
  page.on("response", (response) => {
    if (!response.url().includes("/api/") && !response.url().includes("/health/")) {
      return;
    }
    responseReads.push(
      response
        .text()
        .then((body) => responseBodies.push(body))
        .catch(() => undefined),
    );
  });

  await page.goto(appUrl);
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("StrongPassword123!");
  await page.getByRole("button", { name: "创建管理员" }).click();
  await expect(page.getByRole("heading", { name: "任务列表" })).toBeVisible();

  await page.getByRole("link", { name: "设置", exact: true }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "测试默认配置" })).toBeVisible();
  await expect(page.getByLabel("姓名")).toHaveValue("admin");
  await expect(page.getByLabel("邮箱")).toHaveValue("admin@example.com");

  await page.getByLabel("Access Key ID").fill(ACCESS_KEY_ID);
  await page.getByLabel("Secret Access Key").fill(SECRET_ACCESS_KEY);
  await page.getByLabel("Product ID").fill("product-loop3");
  await page.getByLabel("TOS Bucket").fill("loop3-e2e-bucket");
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

  await page.reload();
  await expect(page.getByLabel("Product ID")).toHaveValue("product-loop3");
  await expect(page.getByLabel("Pod ID")).toHaveCount(0);
  await expect(page.getByLabel("Access Key ID")).toHaveValue("");
  await expect(page.getByLabel("Secret Access Key")).toHaveValue("");
  await expect(page.getByLabel("Ark API Key")).toHaveCount(0);
  await expect(page.getByText(/已配置：AKLT.*7890/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "重新诊断" }),
  ).toHaveCount(0);
  await test.step("Mobile Use 保存刷新后扫描页面秘密", async () => {
    await expectPageSecretsAbsent(page, "Mobile Use 保存刷新后");
  });

  await page.getByRole("link", { name: "刷新与查看 Pod 池" }).click();
  await expect(page).toHaveURL(/\/pods$/);
  await expect(page.getByText("pod-loop3", { exact: true })).toBeVisible();
  await expect(page.getByText("已关机", { exact: true })).toBeVisible();
  const poolSnapshot = await page.request.get(`${appUrl}/api/v1/pod-pool`);
  expect(poolSnapshot.status()).toBe(200);
  expect(await poolSnapshot.json()).toMatchObject({
    items: [
      {
        pod_id: "pod-loop3",
        pod_status_code: 2,
        request_id: "req-loop3-list",
      },
    ],
  });
  await expect(
    page.getByRole("button", { name: /删除|重启|关机/ }),
  ).toHaveCount(0);
  await test.step("Pod 池展示后扫描页面秘密", async () => {
    await expectPageSecretsAbsent(page, "Pod 池展示后");
  });

  await mkdir(SCREENSHOT_DIR, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    fullPage: true,
    path: join(SCREENSHOT_DIR, "desktop-pod-pool-unavailable.png"),
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);

  await page.getByRole("link", { name: "设置", exact: true }).click();
  await expect(page.getByRole("heading", { name: "通知设置" })).toHaveCount(0);
  await expect(page.getByLabel("短信通知")).toHaveCount(0);
  await expect(page.getByText("任务执行失败")).toHaveCount(0);
  await test.step("最终设置页扫描页面秘密", async () => {
    await expectPageSecretsAbsent(page, "最终设置页");
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    fullPage: true,
    path: join(SCREENSHOT_DIR, "mobile-mock-passed.png"),
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);

  await writeFile(notReadyFile, "not ready");
  const readiness = await page.request.get(`${appUrl}/health/ready`);
  expect(readiness.status()).toBe(503);
  expect(await readiness.json()).toMatchObject({
    status: "not_ready",
    failed_checks: ["database"],
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
  await expect(page.getByLabel("Product ID")).toHaveValue("product-loop3");
  await rm(notReadyFile);

  await Promise.all(responseReads);
  const renderedText = await page.locator("body").innerText();
  const observableOutput = [renderedText, ...responseBodies].join("\n");
  for (const secret of [ACCESS_KEY_ID, SECRET_ACCESS_KEY, ARK_API_KEY]) {
    expect(observableOutput).not.toContain(secret);
  }
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});
