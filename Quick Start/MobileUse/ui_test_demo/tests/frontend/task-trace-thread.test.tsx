import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

import { renderApp, server, user } from "./setup";

const STYLES = readFileSync("web/styles.css", "utf8");

const runningTask = {
  id: "task_trace",
  case_id: "case_1",
  script_version_id: null,
  prompt_snapshot: null,
  result_summary: "完成",
  result_evidence: [],
  remote_thread_id: "thread-xyz",
  remote_status_code: 2,
  remote_step_id: "step-current",
  recording_url: null,
  result_assets: {},
  runner_type: "mobile_use",
  scenario: "轨迹任务",
  execution_status: "running",
  verdict: null,
  failure_type: null,
  version: 1,
  created_at: "2026-07-28T03:35:00Z",
  started_at: "2026-07-28T03:35:10Z",
  finished_at: null,
  created_by: "admin",
};

const completedTask = {
  ...runningTask,
  execution_status: "result_ready",
  verdict: "pass",
  finished_at: "2026-07-28T03:40:00Z",
  remote_status_code: 3,
};

it("keeps the current step and realtime stream side by side on desktop", () => {
  expect(STYLES).toMatch(
    /\.trace-runtime-layout\s*{[^}]*grid-template-columns:\s*minmax\(420px,\s*0\.9fr\)\s+minmax\(520px,\s*0\.75fr\);[^}]*}/s,
  );
});

it("renders trace timeline with current step during execution", async () => {
  server.use(
    http.get("/api/v1/tasks/task_trace", () => HttpResponse.json(runningTask)),
    http.get("/api/v1/tasks/task_trace/runtime", () =>
      HttpResponse.json({
        task: runningTask,
        current_step: {
          run_id: "run-current",
          thread_id: "thread-xyz",
          status: 2,
          step_id: "step-current",
          results: [
            {
              Action: "observe",
              Param: { content: "看到首页视频流" },
              StepResult: { IsSuccess: true, Result: "观察成功" },
              Timestamp: "2026-07-28T11:35:20+08:00",
            },
          ],
        },
        thread_groups: [
          {
            thread_id: "thread-xyz",
            task_next_token: null,
            tasks: [
              {
                run_id: "run-current",
                thread_id: "thread-xyz",
                run_name: "轨迹任务",
                status: 2,
                pod_id: "pod-1",
                product_id: "prod-1",
                created_at: "2026-07-28 11:35:10 +0800 CST",
                started_at: "2026-07-28 11:35:12 +0800 CST",
                updated_at: "2026-07-28 11:35:20 +0800 CST",
                completed_at: null,
                trace_id: "trace-xyz",
                artifact_count: { Screenshot: 2 },
              },
            ],
          },
        ],
        thread_steps: [
          {
            run_id: "run-current",
            thread_id: "thread-xyz",
            status: 2,
            step_id: "step-current",
            results: [
              {
                Action: "tap-history",
                Param: { x: 100, y: 200 },
                StepResult: { IsSuccess: true, Result: "历史点击成功" },
                Timestamp: "2026-07-28T11:35:10+08:00",
              },
            ],
          },
        ],
        result: {
          summary: null,
          evidence: [],
          recording_url: null,
          assets: {},
        },
        errors: {},
      }),
    ),
  );

  renderApp("/tasks/task_trace/trace");

  expect(await screen.findByText("当前步骤")).toBeVisible();
  expect(screen.getAllByText("observe").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("拉流画面")).toBeVisible();
  expect(screen.getByLabelText("云手机实时画面")).toBeVisible();
  expect(screen.queryByText("执行步骤详情")).not.toBeInTheDocument();
  expect(screen.queryByText("tap-history")).not.toBeInTheDocument();
  expect(screen.getByText("自动刷新中")).toBeVisible();
});

it("shows all tools from thread_steps on the timeline after completion", async () => {
  server.use(
    http.get("/api/v1/tasks/task_trace", () => HttpResponse.json(completedTask)),
    http.get("/api/v1/tasks/task_trace/runtime", () =>
      HttpResponse.json({
        task: completedTask,
        current_step: {
          run_id: "run-current",
          thread_id: "thread-xyz",
          status: 3,
          step_id: "finished",
          results: [
            {
              Action: "finished",
              Param: { content: "任务完成" },
              StepResult: { IsSuccess: true, Result: "任务完成" },
              Timestamp: "2026-07-28T11:40:00+08:00",
            },
          ],
        },
        thread_groups: [],
        execution_config: { pod_id: "pod-1" },
        thread_steps: [{
          run_id: "run-current",
          thread_id: "thread-xyz",
          status: 2,
          step_id: "step-current",
          results: [
            {
              Action: "observe",
              Param: { content: "看到首页视频流" },
              StepResult: { IsSuccess: true, Result: "观察成功" },
              Timestamp: "2026-07-28T11:35:20+08:00",
            },
            {
              Action: "tap",
              Param: { x: 100, y: 200 },
              StepResult: { IsSuccess: true, Result: "点击成功" },
              Timestamp: "2026-07-28T11:35:30+08:00",
            },
          ],
        }],
        result: { summary: null, evidence: [], recording_url: null, assets: {} },
        errors: {},
      }),
    ),
  );

  renderApp("/tasks/task_trace/trace");

  await screen.findByText("执行步骤详情");
  expect(screen.queryByText("当前步骤")).not.toBeInTheDocument();
  expect(screen.getByText("拉流画面")).toBeVisible();
  expect(screen.getByLabelText("云手机实时画面")).toBeVisible();
  expect(screen.getByText("observe")).toBeVisible();
  expect(screen.getByText("tap")).toBeVisible();
});

it("shows the latest twenty completed steps by default and can expand all", async () => {
  const results = Array.from({ length: 25 }, (_, index) => ({
    Action: `action-${index + 1}`,
    Param: { index: index + 1 },
    StepResult: { IsSuccess: true, Result: `result-${index + 1}` },
    Timestamp: `2026-07-28T11:${String(index + 1).padStart(2, "0")}:00+08:00`,
  }));
  server.use(
    http.get("/api/v1/tasks/task_trace", () => HttpResponse.json(completedTask)),
    http.get("/api/v1/tasks/task_trace/runtime", () =>
      HttpResponse.json({
        task: completedTask,
        current_step: null,
        thread_groups: [],
        execution_config: { pod_id: "pod-1" },
        thread_steps: [{
          run_id: "run-current",
          thread_id: "thread-xyz",
          status: 3,
          step_id: "finished",
          results,
        }],
        result: { summary: null, evidence: [], recording_url: null, assets: {} },
        errors: {},
      }),
    ),
  );

  renderApp("/tasks/task_trace/trace");

  await screen.findByText("执行步骤详情");
  expect(screen.queryByText("action-1")).not.toBeInTheDocument();
  expect(screen.getByText("action-6")).toBeVisible();
  expect(screen.getByText("action-25")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "展开全部 25 步" }));
  expect(screen.getByText("action-1")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "收起到最近 20 步" }));
  expect(screen.queryByText("action-1")).not.toBeInTheDocument();
  expect(screen.getByText("action-25")).toBeVisible();
});

it("hides current step card when task is completed", async () => {
  server.use(
    http.get("/api/v1/tasks/task_trace", () => HttpResponse.json(completedTask)),
    http.get("/api/v1/tasks/task_trace/runtime", () =>
      HttpResponse.json({
        task: completedTask,
        current_step: {
          run_id: "run-current",
          thread_id: "thread-xyz",
          status: 3,
          step_id: "finished",
          results: [
            {
              Action: "finished",
              Param: { content: "任务完成" },
              StepResult: { IsSuccess: true, Result: "任务完成" },
              Timestamp: "2026-07-28T11:40:00+08:00",
            },
          ],
        },
        thread_groups: [],
        thread_steps: [
          {
            run_id: "run-current",
            thread_id: "thread-xyz",
            status: 3,
            step_id: "finished",
            results: [
              {
                Action: "observe",
                Param: { content: "看到首页" },
                StepResult: { IsSuccess: true, Result: "观察成功" },
                Timestamp: "2026-07-28T11:35:20+08:00",
              },
              {
                Action: "tap",
                Param: { x: 100, y: 200 },
                StepResult: { IsSuccess: true, Result: "点击成功" },
                Timestamp: "2026-07-28T11:35:30+08:00",
              },
              {
                Action: "finished",
                Param: { content: "任务完成" },
                StepResult: { IsSuccess: true, Result: "任务完成" },
                Timestamp: "2026-07-28T11:40:00+08:00",
              },
            ],
          },
        ],
        result: { summary: "任务完成", evidence: [], recording_url: null, assets: {} },
        errors: {},
      }),
    ),
  );

  renderApp("/tasks/task_trace/trace");

  await screen.findByText("执行步骤详情");
  expect(screen.queryByText("当前步骤")).not.toBeInTheDocument();
  expect(screen.queryByText("自动刷新中")).not.toBeInTheDocument();
  expect(await screen.findByText("observe")).toBeVisible();
  expect(screen.getByText("tap")).toBeVisible();
  expect(screen.getByText("finished")).toBeVisible();
});
