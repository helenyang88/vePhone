import { readFileSync } from "node:fs";

import { screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { expectCsrf, renderApp, server, user } from "./setup";

const STYLES = readFileSync("web/styles.css", "utf8");

const adminUser = {
  id: 1,
  username: "admin",
  display_name: null,
  email: null,
  role: "admin",
  status: "active",
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
  last_login_at: null,
};

const memberUser = {
  id: 2,
  username: "alice",
  display_name: "Alice",
  email: "alice@example.com",
  role: "member",
  status: "active",
  created_at: "2026-07-25T00:00:00Z",
  updated_at: "2026-07-25T00:00:00Z",
  last_login_at: null,
};

it("allows administrators to batch create users, edit roles, and reset passwords", async () => {
  let createBody: unknown;
  let rolePatchBody: unknown;
  let resetBody: unknown;
  server.use(
    http.get("/api/v1/users", () => HttpResponse.json({ items: [adminUser, memberUser] })),
    http.post("/api/v1/users/batch", async ({ request }) => {
      expectCsrf(request);
      createBody = await request.json();
      return HttpResponse.json(
        { items: [
          {
            id: 3,
            username: "bob",
            display_name: "Bob",
            email: "bob@example.com",
            role: "admin",
            status: "active",
            created_at: "2026-07-26T00:00:00Z",
            updated_at: "2026-07-26T00:00:00Z",
            last_login_at: null,
          },
        ] },
        { status: 201 },
      );
    }),
    http.patch("/api/v1/users/2", async ({ request }) => {
      expectCsrf(request);
      rolePatchBody = await request.json();
      return HttpResponse.json({ ...memberUser, role: "admin" });
    }),
    http.post("/api/v1/users/2/reset-password", async ({ request }) => {
      expectCsrf(request);
      resetBody = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );

  renderApp("/users");

  expect(await screen.findByRole("heading", { name: "用户管理" })).toBeVisible();
  expect(screen.getByText("admin")).toBeVisible();
  expect(await screen.findByText("alice")).toBeVisible();
  expect(screen.queryByText("已有表格？可以批量粘贴导入")).not.toBeInTheDocument();
  expect(screen.queryByText(/粘贴解析/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "即将支持" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "添加一行" })).toHaveClass("user-batch-action");
  expect(screen.getByRole("button", { name: "批量创建用户" })).toHaveClass("user-batch-action");

  await user.type(screen.getByLabelText("用户名 1"), "bob");
  await user.type(screen.getByLabelText("显示名称 1"), "Bob");
  await user.type(screen.getByLabelText("邮箱 1"), "bob@example.com");
  await user.type(screen.getByLabelText("初始密码 1"), "StrongPassword123!");
  await user.click(screen.getByRole("combobox", { name: "角色 1" }));
  await user.click(screen.getByRole("option", { name: "管理员" }));
  await user.click(screen.getByRole("button", { name: "批量创建用户" }));

  await waitFor(() =>
    expect(createBody).toEqual({
      users: [
        {
          username: "bob",
          display_name: "Bob",
          email: "bob@example.com",
          password: "StrongPassword123!",
          role: "admin",
        },
      ],
    }),
  );

  const aliceRow = screen.getByRole("row", { name: /alice/ });
  await user.click(within(aliceRow).getByRole("combobox", { name: "alice 角色" }));
  await user.click(screen.getByRole("option", { name: "管理员" }));
  await waitFor(() => expect(rolePatchBody).toEqual({ role: "admin" }));

  await user.click(within(aliceRow).getByRole("button", { name: "重置密码" }));
  await user.type(screen.getByLabelText("新密码"), "ResetPassword123!");
  await user.type(screen.getByLabelText("确认新密码"), "ResetPassword123!");
  await user.click(screen.getByRole("button", { name: "确认重置" }));

  await waitFor(() =>
    expect(resetBody).toEqual({
      new_password: "ResetPassword123!",
      confirm_password: "ResetPassword123!",
    }),
  );
  expect(screen.getByText("密码已重置。")).toBeVisible();
});

it("uses fixed equal width for batch action buttons", () => {
  expect(STYLES).toMatch(
    /\.user-batch-header\s*\{[^}]*display:\s*flex;[^}]*justify-content:\s*space-between;/s,
  );
  expect(STYLES).toMatch(
    /\.user-batch-actions\s+\.user-batch-action\s*\{[^}]*flex:\s*0 0 128px;[^}]*height:\s*36px;[^}]*width:\s*128px;/s,
  );
  expect(STYLES).toMatch(
    /\.user-batch-actions\s*\{[^}]*margin-left:\s*auto;[^}]*justify-content:\s*flex-end;/s,
  );
});

it("redirects members away from user management", async () => {
  server.use(
    http.get("/api/v1/auth/me", () =>
      HttpResponse.json({ ...memberUser, display_name: "Alice" })),
  );

  renderApp("/users");

  await waitFor(() =>
    expect(screen.queryByRole("heading", { name: "用户管理" }))
      .not.toBeInTheDocument(),
  );
  expect(await screen.findByRole("heading", { name: "执行记录" })).toBeVisible();
});

it("allows members to open the pod pool page", async () => {
  server.use(
    http.get("/api/v1/auth/me", () =>
      HttpResponse.json({ ...memberUser, display_name: "Alice" })),
    http.get("/api/v1/pod-pool", () =>
      HttpResponse.json({ refreshed_at: null, items: [] })),
  );

  renderApp("/pods");

  expect(await screen.findByRole("heading", { name: "设备池" })).toBeVisible();
});
