import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { expectCsrf, renderApp, server, user } from "./setup";

describe("authentication gate", () => {
  it("shows setup before the first admin exists", async () => {
    server.use(
      http.get("/api/v1/setup/status", () => HttpResponse.json({ initialized: false })),
    );

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "初始化管理员" })).toBeVisible();
    expect(screen.getByLabelText("用户名")).toBeVisible();
    expect(screen.getByLabelText("密码")).toHaveAttribute("type", "password");
  });

  it("redirects anonymous initialized users to login", async () => {
    server.use(
      http.get("/api/v1/auth/me", () => new HttpResponse(null, { status: 401 })),
    );

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeVisible();
    expect(screen.getByRole("heading", { name: /让移动端自动化测试/ })).toBeVisible();
    expect(screen.getByText("让移动端自动化测试")).toHaveClass("auth-title-primary");
    expect(screen.getByText("用例库与测试计划统一维护")).toBeVisible();
    expect(screen.getByText("Mobile Use 真机执行链路")).toBeVisible();
    expect(screen.getByText("Trace、截图与结构化结果沉淀")).toBeVisible();
    expect(screen.getByText("还没有账号？")).toBeVisible();
    expect(screen.getByRole("link", { name: "联系管理员开通" })).toBeVisible();
    expect(screen.queryByText(/© 2024 MUA Test/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "服务条款" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "隐私政策" })).not.toBeInTheDocument();
    expect(screen.queryByText(/AI 自动生成可执行脚本/)).not.toBeInTheDocument();
  });

  it("switches setup to login when another request initialized the admin", async () => {
    let initialized = false;
    server.use(
      http.get("/api/v1/setup/status", () => HttpResponse.json({ initialized })),
      http.post("/api/v1/setup/admin", ({ request }) => {
        expectCsrf(request);
        initialized = true;
        return HttpResponse.json(
          {
            error: {
              code: "admin_already_initialized",
              message: "Administrator has already been initialized",
              request_id: "req_conflict",
              details: {},
            },
          },
          { status: 409 },
        );
      }),
      http.get("/api/v1/auth/me", () => new HttpResponse(null, { status: 401 })),
    );
    renderApp("/");

    await user.type(await screen.findByLabelText("用户名"), "admin");
    await user.type(screen.getByLabelText("密码"), "StrongPassword123!");
    await user.click(screen.getByRole("button", { name: "创建管理员" }));

    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeVisible();
  });

  it("enters the task list after login", async () => {
    server.use(
      http.get("/api/v1/auth/me", () => new HttpResponse(null, { status: 401 })),
      http.post("/api/v1/auth/login", async ({ request }) => {
        expect(await request.json()).toEqual({
          username: "admin",
          password: "StrongPassword123!",
        });
        return HttpResponse.json({
          id: 1,
          username: "admin",
          created_at: "2026-07-24T00:00:00Z",
        });
      }),
    );
    renderApp("/");

    await user.type(await screen.findByLabelText("用户名"), "admin");
    await user.type(screen.getByLabelText("密码"), "StrongPassword123!");
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("heading", { name: "执行记录" })).toBeVisible();
  });

  it("renders authenticated tasks with readable statuses", async () => {
    server.use(
      http.get("/api/v1/tasks", () =>
        HttpResponse.json({
          items: [
            {
              id: "task_1",
              case_id: "case_1",
              script_version_id: "script_1",
              runner_type: "mock",
              scenario: "success",
              execution_status: "result_ready",
              verdict: "pass",
              failure_type: null,
              version: 3,
              created_at: "2026-07-24T08:00:00Z",
              started_at: "2026-07-24T08:00:01Z",
              finished_at: "2026-07-24T08:00:02Z",
            },
          ],
        }),
      ),
    );

    renderApp("/");

    expect(await screen.findByText("task_1")).toBeVisible();
    expect(screen.getByText("已完成")).toBeVisible();
    expect(screen.getByText("成功")).toBeVisible();
  });

  it("clears cached authentication when a business request returns 401", async () => {
    server.use(
      http.get("/api/v1/tasks", () =>
        HttpResponse.json(
          {
            error: {
              code: "authentication_required",
              message: "Authentication required",
              request_id: "req_expired",
              details: {},
            },
          },
          { status: 401 },
        ),
      ),
    );

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeVisible();
  });
});
