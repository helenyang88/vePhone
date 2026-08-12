import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it, vi } from "vitest";

import { renderApp, server, user } from "./setup";

const task = {
  id: "task_runtime",
  case_id: "case_1",
  script_version_id: null,
  prompt_snapshot: "## 执行任务\n打开抖音APP查看3个视频",
  result_summary: "已打开抖音并完成浏览",
  result_evidence: ["首页出现视频流", "已滑动 3 个视频"],
  remote_thread_id: "thread-123",
  remote_status_code: 3,
  remote_step_id: "finished",
  recording_url: "https://example.invalid/replay.mp4",
  result_assets: {
    usage: { in_tokens: 100, out_tokens: 20 },
    screenshots: {
      "003-third": { original_screenshot: "https://example.invalid/s3-original.png" },
      "001-first": { screenshot: "https://example.invalid/s1.png" },
      "002-second": { screenshot: "https://example.invalid/s2.png" },
    },
    files: ["/sdk_files/run-1/log.txt", "/sdk_files/run-1/result.json"],
  },
  runner_type: "mobile_use",
  scenario: "打开抖音APP查看3个视频",
  execution_config: {
    source: "custom",
    product_id: "prod-1",
    pod_id: "pod-1",
    tos_bucket: "custom-bucket",
    tos_endpoint: "tos-s3-cn-beijing.volces.com",
    tos_region: "cn-beijing",
    timeout_seconds: 456,
    use_base64_screenshot: false,
    max_step: 123,
    callback_info: { url: "https://callback.example.com" },
    output_schema: "{\"type\":\"object\"}",
    retry_limit: 7,
    system_prompt: "custom system prompt",
    screen_record: true,
    mcp_json: "{\"mcpServers\":{\"amap\":{\"url\":\"https://mcp.example.com\"}}}",
    max_output_tokens: 2048,
    gps_info: "116.397128,39.916527,50,0,0,10",
    request_headers: {
      configured: true,
      names: ["X-Env", "X-Api-Key"],
      items: [
        { name: "X-Env", value: "staging" },
        { name: "X-Api-Key", value: "sk_l***cdef" },
      ],
    },
  },
  execution_status: "result_ready",
  verdict: "pass",
  failure_type: null,
  version: 4,
  created_at: "2026-07-28T03:35:31.564869Z",
  started_at: "2026-07-28T03:35:31.575333Z",
  finished_at: "2026-07-28T03:38:32.263965Z",
  created_by: "admin",
};

function runtimePayload() {
  return {
    task,
    execution_config: task.execution_config,
    current_step: {
      run_id: "run-1",
      thread_id: "thread-123",
      status: 3,
      step_id: "finished",
      results: [
        {
          Action: "finished",
          Param: { content: "任务已完成" },
          StepResult: { IsSuccess: true, Result: "任务已完成" },
          Timestamp: "2026-07-28T11:38:32+08:00",
        },
      ],
    },
    thread_groups: [
      {
        thread_id: "thread-123",
        task_next_token: null,
        tasks: [
          {
            run_id: "run-1",
            thread_id: "thread-123",
            run_name: "打开抖音",
            status: 3,
            pod_id: "pod-1",
            product_id: "prod-1",
            created_at: "2026-07-28 11:35:31 +0800 CST",
            started_at: "2026-07-28 11:35:32 +0800 CST",
            updated_at: "2026-07-28 11:38:32 +0800 CST",
            completed_at: "2026-07-28 11:38:32 +0800 CST",
            trace_id: "trace-1",
            artifact_count: { Screenshot: 3, Video: 1 },
          },
        ],
      },
    ],
    thread_steps: [
      {
        run_id: "run-1",
        thread_id: "thread-123",
        status: 3,
        step_id: "finished",
        results: [
          {
            Action: "tap",
            Param: { x: 100, y: 200 },
            StepResult: { IsSuccess: true, Result: "点击成功" },
            Timestamp: "2026-07-28T11:36:00+08:00",
          },
        ],
      },
    ],
    result: {
      summary: "已打开抖音并完成浏览",
      evidence: ["首页出现视频流", "已滑动 3 个视频"],
      recording_url: "https://example.invalid/replay.mp4",
      assets: task.result_assets,
    },
    errors: {},
  };
}

it("renders result-first overview with four KPIs, carousel screenshots and separated files", async () => {
  server.use(
    http.get("/api/v1/tasks/task_runtime", () => HttpResponse.json(task)),
    http.get("/api/v1/tasks/task_runtime/runtime", () =>
      HttpResponse.json(runtimePayload()),
    ),
  );

  const { container } = renderApp("/tasks/task_runtime");

  expect(await screen.findByText("运行总览")).toBeVisible();
  const meta = screen.getByLabelText("运行元信息");
  expect(meta).toHaveClass("runtime-metric-strip");
  expect(meta).toHaveClass("runtime-metric-strip--bare");
  expect(meta).toHaveClass("runtime-metric-strip--full-labels");
  expect(meta.querySelectorAll(".runtime-metric-pill")).toHaveLength(5);
  expect(meta.querySelectorAll(".runtime-metric-glyph")).toHaveLength(5);
  expect(meta.querySelector(".runtime-metric-pill.status")).toBeInTheDocument();
  expect(meta.querySelector(".runtime-metric-pill.token-in")).toBeInTheDocument();
  expect(meta.querySelector(".runtime-metric-pill.token-out")).toBeInTheDocument();
  expect(meta.querySelector(".runtime-metric-pill.duration")).toBeInTheDocument();
  expect(meta.querySelector(".runtime-metric-pill.steps")).toBeInTheDocument();
  expect(meta.querySelector(".runtime-kpi-card")).not.toBeInTheDocument();
  expect(within(meta).getByText("远端状态")).toBeVisible();
  expect(within(meta).getByText("输入 Tokens")).toBeVisible();
  expect(within(meta).getByText("输出 Tokens")).toBeVisible();
  expect(within(meta).getByText("运行总时间")).toBeVisible();
  expect(within(meta).getByText("执行步数")).toBeVisible();
  expect(within(meta).getByText("已完成")).toBeVisible();
  expect(within(meta).getByText("100")).toBeVisible();
  expect(within(meta).getByText("20")).toBeVisible();
  expect(within(meta).getByText("03:00")).toBeVisible();
  await waitFor(() => expect(within(meta).getByText("1")).toBeVisible());
  expect(within(meta).queryByText("ThreadID")).not.toBeInTheDocument();
  expect(within(meta).queryByText("RunID")).not.toBeInTheDocument();

  const resultCard = screen.getByText("执行结果").closest("section");
  expect(resultCard).not.toBeNull();
  expect(within(resultCard!).getByText("成功")).toBeVisible();
  expect(screen.getByText("已打开抖音并完成浏览")).toBeVisible();
  expect(screen.getByText("查看录制回放")).toHaveAttribute(
    "href",
    "https://example.invalid/replay.mp4",
  );
  const detailNavigation = screen.getByRole("navigation", {
    name: "任务详情导航",
  });
  expect(within(detailNavigation).queryByRole("link", { name: /报告/ }))
    .not.toBeInTheDocument();
  expect(screen.queryByText("当前步骤")).not.toBeInTheDocument();
  expect(screen.getByText("执行截图")).toBeVisible();
  expect(screen.getByText("1 / 3")).toBeVisible();
  const image = screen.getByRole("img", { name: "截图 1" });
  expect(image).toHaveAttribute(
    "src",
    "https://example.invalid/s1.png",
  );
  // Expired screenshots are dropped from the viewer instead of showing a placeholder.
  fireEvent.error(image);
  expect(screen.getByText("1 / 2")).toBeVisible();
  expect(screen.queryByText("截图已过期或无法访问")).not.toBeInTheDocument();

  const video = container.querySelector("video");
  fireEvent.error(video!);
  expect(screen.getByText("录制回放已过期或无法访问")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "下一张截图" }));
  expect(screen.getByText("2 / 2")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "上一张截图" }));
  expect(screen.getByText("1 / 2")).toBeVisible();

  expect(screen.getByText("结果文件")).toBeVisible();
  expect(screen.getByText("/sdk_files/run-1/log.txt")).toBeVisible();
  expect(screen.getByText("/sdk_files/run-1/result.json")).toBeVisible();
  const taskInfoCard = screen.getByText("任务信息").closest("section");
  expect(taskInfoCard).not.toBeNull();
  expect(within(taskInfoCard!).getAllByText("2026-07-28 11:35:31")).toHaveLength(2);
  expect(within(taskInfoCard!).getByText("2026-07-28 11:38:32")).toBeVisible();
  expect(within(taskInfoCard!).queryByText("版本")).not.toBeInTheDocument();

  const configCard = screen.getByText("运行配置快照").closest("section");
  expect(configCard).not.toBeNull();
  expect(within(configCard!).getByText("自定义配置")).toBeVisible();
  expect(within(configCard!).getByText("执行边界")).toBeVisible();
  expect(within(configCard!).getByText("采集能力")).toBeVisible();
  expect(within(configCard!).getByText("存储与扩展")).toBeVisible();
  expect(within(configCard!).getByText("456 s")).toBeVisible();
  const headerRow = within(configCard!).getByText("请求 Header")
    .closest(".runtime-config-row");
  expect(headerRow).not.toBeNull();
  const headerButton = within(headerRow as HTMLElement).getByRole("button", {
    name: "查看请求 Header",
  });
  expect(headerButton).toHaveTextContent("已设置");
  await user.click(headerButton);
  const headerDialog = await screen.findByRole("dialog", { name: "请求 Header" });
  expect(within(headerDialog).getByText("X-Env")).toBeVisible();
  expect(within(headerDialog).getByText("staging")).toBeVisible();
  expect(within(headerDialog).getByText("X-Api-Key")).toBeVisible();
  expect(within(headerDialog).getByText("sk_l***cdef")).toBeVisible();
  expect(within(headerDialog).getByText("Header 值已按敏感字段规则脱敏。"))
    .toBeVisible();
  await user.click(
    within(headerDialog).getByRole("button", { name: "关闭请求 Header 弹窗" }),
  );
  expect(screen.queryByRole("dialog", { name: "请求 Header" })).not.toBeInTheDocument();
  expect(within(configCard!).queryByText("custom system prompt")).not.toBeInTheDocument();

  const advancedButton = within(configCard!).getByRole("button", {
    name: "查看高级配置",
  });
  expect(advancedButton).toHaveAttribute("aria-expanded", "false");
  await user.click(advancedButton);
  expect(advancedButton).toHaveAttribute("aria-expanded", "true");
  expect(within(configCard!).getByText("custom system prompt")).toBeVisible();
  expect(within(configCard!).getByText(/mcpServers/)).toBeVisible();
  expect(screen.queryByText("Thread 轨迹")).not.toBeInTheDocument();
  expect(screen.queryByText("tap")).not.toBeInTheDocument();
});

it("labels inherited snapshots as global configuration", async () => {
  const globalExecutionConfig = {
    ...task.execution_config,
    source: "global",
    pod_id: null,
    callback_info: null,
    output_schema: null,
    mcp_json: null,
    gps_info: null,
    request_headers: { configured: false, names: [] },
  };
  const globalTask = {
    ...task,
  };
  server.use(
    http.get("/api/v1/tasks/task_runtime", () => HttpResponse.json(globalTask)),
    http.get("/api/v1/tasks/task_runtime/runtime", () =>
      HttpResponse.json({
        ...runtimePayload(),
        task: globalTask,
        execution_config: globalExecutionConfig,
      }),
    ),
  );

  renderApp("/tasks/task_runtime");

  const configCard = (await screen.findByText("运行配置快照")).closest("section");
  expect(configCard).not.toBeNull();
  expect(within(configCard!).getByText("全局配置")).toBeVisible();
  expect(within(configCard!).getByText(/任务创建时继承的全局配置快照/)).toBeVisible();
  expect(within(configCard!).getByText("自动分配")).toBeVisible();
});

it("updates running duration from local timestamps", async () => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
  try {
    vi.setSystemTime(new Date("2026-07-28T03:36:01.000Z"));
    const runningTask = {
      ...task,
      execution_status: "running",
      remote_status_code: 2,
      started_at: "2026-07-28T03:35:31.000Z",
      finished_at: null,
      verdict: null,
    };

    server.use(
      http.get("/api/v1/tasks/task_runtime", () => HttpResponse.json(runningTask)),
      http.get("/api/v1/tasks/task_runtime/runtime", () =>
        HttpResponse.json({
          ...runtimePayload(),
          task: runningTask,
          current_step: {
            ...runtimePayload().current_step,
            status: 2,
          },
        }),
      ),
    );

    const { container } = renderApp("/tasks/task_runtime");

    const meta = await screen.findByLabelText("运行元信息");
    expect(within(meta).getByText("00:30")).toBeVisible();
    expect(container.querySelector(".runtime-metric-pill.steps strong")).toHaveTextContent("-");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(within(meta).getByText("00:35")).toBeVisible();
  } finally {
    vi.useRealTimers();
  }
});

it("keeps queued task duration at zero instead of counting from creation", async () => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
  try {
    vi.setSystemTime(new Date("2026-07-28T04:36:01.000Z"));
    const queuedTask = {
      ...task,
      execution_status: "queued",
      remote_status_code: 1,
      created_at: "2026-07-28T03:35:31.000Z",
      started_at: null,
      finished_at: null,
      verdict: null,
    };

    server.use(
      http.get("/api/v1/tasks/task_runtime", () => HttpResponse.json(queuedTask)),
      http.get("/api/v1/tasks/task_runtime/runtime", () =>
        HttpResponse.json({
          ...runtimePayload(),
          task: queuedTask,
          current_step: null,
        }),
      ),
    );

    renderApp("/tasks/task_runtime");

    const meta = await screen.findByLabelText("运行元信息");
    expect(within(meta).getByText("00:00")).toBeVisible();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(within(meta).getByText("00:00")).toBeVisible();
    expect(within(meta).queryByText("01:00:35")).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});
