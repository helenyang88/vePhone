import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { PodPoolResponse, Task, TestCaseListResponse } from "../../web/api/types";
import { expectCsrf, renderApp, server, user } from "./setup";

const caseList: TestCaseListResponse = {
  total: 1,
  page: 1,
  page_size: 10,
  items: [
    {
      id: "case_1",
      title: "打开抖音APP，查看2个视频",
      module: null,
      content_markdown: "## 执行任务\n打开抖音APP，查看2个视频",
      tags: ["P0"],
      automation_level: "auto",
      execution_count: 0,
      pass_count: 0,
      fail_count: 0,
      last_executed_at: null,
      created_by: "admin",
      created_at: "2026-07-28T03:00:00Z",
      updated_at: "2026-07-28T03:00:00Z",
    },
  ],
};

const refreshedPool: PodPoolResponse = {
  refreshed_at: "2026-07-28T03:30:00Z",
  items: [],
};

const createdTask: Task = {
  id: "task_123",
  case_id: "case_1",
  script_version_id: null,
  prompt_snapshot: null,
  result_summary: null,
  result_evidence: [],
  runner_type: "mobile_use",
  scenario: "打开抖音APP，查看2个视频",
  created_by: "admin",
  execution_status: "queued",
  verdict: null,
  failure_type: null,
  version: 1,
  created_at: "2026-07-28T03:31:00Z",
  started_at: null,
  finished_at: null,
};

describe("用例库执行", () => {
  it("执行成功后跳转到后端返回的任务 id", async () => {
    let requestedTaskId = "";
    server.use(
      http.get("/api/v1/cases", () => HttpResponse.json(caseList)),
      http.get("/api/v1/cases/tags", () => HttpResponse.json({ items: ["P0"] })),
      http.get("/api/v1/cases/modules", () => HttpResponse.json({ items: [] })),
      http.post("/api/v1/pod-pool/refresh", ({ request }) => {
        expectCsrf(request);
        return HttpResponse.json(refreshedPool);
      }),
      http.post("/api/v1/cases/case_1/execute", ({ request }) => {
        expectCsrf(request);
        return HttpResponse.json(createdTask, { status: 201 });
      }),
      http.get("/api/v1/tasks/:taskId", ({ params }) => {
        requestedTaskId = String(params.taskId);
        return HttpResponse.json(createdTask);
      }),
    );

    renderApp("/cases");

    await screen.findByRole("link", { name: "打开抖音APP，查看2个视频" });
    await user.click(screen.getByTitle("执行用例"));
    await user.click(await screen.findByRole("button", { name: /开始执行/ }));

    await waitFor(() => expect(requestedTaskId).toBe("task_123"));
  });
});
