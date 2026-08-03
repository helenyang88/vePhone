import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 900 } });

test("creates a specified-device multi-case batch from the four-step wizard", async ({ page }) => {
  const caseItems = [
    {
      id: "case-e2e-a",
      title: "登录链路",
      module: "账号",
      content_markdown: "- 登录",
      tags: ["smoke"],
      automation_level: "auto",
      execution_count: 0,
      pass_count: 0,
      fail_count: 0,
      last_executed_at: null,
      created_by: "admin",
      created_at: "2026-07-29T00:00:00Z",
      updated_at: "2026-07-29T00:00:00Z",
    },
    {
      id: "case-e2e-b",
      title: "搜索链路",
      module: "搜索",
      content_markdown: "- 搜索",
      tags: ["regression"],
      automation_level: "auto",
      execution_count: 0,
      pass_count: 0,
      fail_count: 0,
      last_executed_at: null,
      created_by: "admin",
      created_at: "2026-07-29T00:00:00Z",
      updated_at: "2026-07-29T00:00:00Z",
    },
  ];
  const pod = {
    product_id: "product-e2e",
    pod_id: "pod-e2e-a",
    pod_name: "E2E 云机 A",
    pod_status_code: 1,
    stream_status: null,
    discovery_state: "active",
    local_state: "available",
    image_id: null,
    image_name: null,
    aosp_version: "13",
    display_layout_id: null,
    dc_id: null,
    dc_name: null,
    isp_code: null,
    region: null,
    zone_id: null,
    config_code: "g2",
    config_name: "通用型",
    config_type: 1,
    server_type_code: null,
    intranet_ip: null,
    adb_address: null,
    adb_status: null,
    data_size: null,
    data_size_used: null,
    pod_created_at: null,
    last_seen_at: "2026-07-29T00:00:00Z",
    last_checked_at: null,
    request_id: null,
    task_id: null,
    task_status: null,
    task_scenario: null,
    eip_address: null,
  };
  let submitted: Record<string, unknown> | null = null;

  await page.route("**/api/v1/setup/status", (route) =>
    route.fulfill({ json: { initialized: true } }));
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: { id: 1, username: "admin", created_at: "2026-07-29T00:00:00Z" },
    }));
  await page.route("**/api/v1/cases?*", (route) =>
    route.fulfill({
      json: { items: caseItems, total: 2, page: 1, page_size: 100 },
    }));
  await page.route("**/api/v1/pod-pool", (route) =>
    route.fulfill({
      json: { items: [pod], refreshed_at: "2026-07-29T00:00:00Z" },
    }));
  await page.route("**/api/v1/task-batches", async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      json: {
        id: "batch-e2e-created",
        name: "回归测试 · 2 个用例",
        test_type: "regression",
        selection_mode: "multi_cases",
        selection_snapshot: { case_ids: ["case-e2e-a", "case-e2e-b"] },
        device_strategy: "specified",
        pod_ids: ["pod-e2e-a"],
        concurrency: 2,
        device_wait_timeout_seconds: 300,
        execution_status: "queued",
        verdict: null,
        created_by: "admin",
        unavailable_since: null,
        cancel_requested_at: null,
        created_at: "2026-07-29T00:00:00Z",
        started_at: null,
        finished_at: null,
        tasks: [],
      },
    });
  });

  await page.goto("/tasks/new?step=type");
  await page.getByRole("radio", { name: /回归测试/ }).check();
  await page.getByRole("button", { name: "下一步：选择用例" }).click();
  await page.getByRole("radio", { name: "多用例" }).check();
  await page.getByRole("checkbox", { name: /登录链路/ }).check();
  await page.getByRole("checkbox", { name: /搜索链路/ }).check();
  await page.getByRole("button", { name: "下一步：设备策略" }).click();
  await page.getByRole("radio", { name: /指定设备/ }).check();
  await page.getByLabel("批次并发数").fill("2");
  await page.getByRole("checkbox", { name: /E2E 云机 A/ }).check();
  await page.getByRole("button", { name: "下一步：确认提交" }).click();
  await page.getByRole("button", { name: "打开执行配置" }).click();

  const dialog = page.getByRole("dialog", { name: "执行配置" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS("transform", "none");
  const box = await dialog.boundingBox();
  expect(box?.width).toBe(920);
  expect(box?.height).toBe(680);
  await page.getByRole("button", { name: /开始执行/ }).click();

  await expect(page.getByText("batch-e2e-created")).toBeVisible();
  expect(submitted).toMatchObject({
    test_type: "regression",
    selection_mode: "multi_cases",
    case_ids: ["case-e2e-a", "case-e2e-b"],
    device_strategy: "specified",
    pod_ids: ["pod-e2e-a"],
    concurrency: 2,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
