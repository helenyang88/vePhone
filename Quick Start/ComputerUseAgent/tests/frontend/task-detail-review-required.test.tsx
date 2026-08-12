import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { renderApp, server } from "./setup";

const failedTask = {
  id: "task_review",
  case_id: "case_680a16d47526471eb8f91915be7b13f0",
  script_version_id: null,
  prompt_snapshot: "## 执行任务\n打开抖音APP查看3个视频",
  result_summary: "执行失败：页面卡住",
  result_evidence: ["GetAgentResult Content: 执行失败：页面卡住"],
  runner_type: "mobile_use",
  scenario: "打开抖音APP查看3个视频",
  execution_status: "result_ready",
  verdict: "fail",
  failure_type: "runner_interrupted",
  version: 3,
  created_at: "2026-07-28T03:35:31.564869Z",
  started_at: "2026-07-28T03:35:31.575333Z",
  finished_at: "2026-07-28T03:35:32.263965Z",
  remote_thread_id: "thread-review",
  remote_status_code: 6,
  remote_step_id: "finished",
  recording_url: null,
  result_assets: { usage: { in_tokens: 0, out_tokens: 0 }, screenshots: {}, files: [] },
  created_by: "admin",
};

const failedRuntime = {
  task: failedTask,
  current_step: null,
  thread_groups: [],
  thread_steps: [],
  result: {
    summary: "执行失败：页面卡住",
    evidence: ["GetAgentResult Content: 执行失败：页面卡住"],
    recording_url: null,
    assets: { usage: { in_tokens: 0, out_tokens: 0 }, screenshots: {}, files: [] },
  },
  errors: {},
};

it("shows failed task details when task is interrupted", async () => {
  server.use(
    http.get("/api/v1/tasks/task_review", () => HttpResponse.json(failedTask)),
    http.get("/api/v1/tasks/task_review/runtime", () => HttpResponse.json(failedRuntime)),
  );

  renderApp("/tasks/task_review");

  expect(await screen.findByText(/任务 ID/)).toHaveTextContent("task_review");
  expect(screen.queryByText("任务详情加载失败")).not.toBeInTheDocument();
  expect(screen.getByText("已完成")).toBeVisible();
  expect(screen.getAllByText("失败").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("执行失败：页面卡住")).toBeVisible();
  expect(screen.getByText("GetAgentResult Content: 执行失败：页面卡住")).toBeVisible();
});
