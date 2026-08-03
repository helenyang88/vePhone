import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";

import { AppShell } from "../../web/components/app-shell";
import type { User } from "../../web/api/types";

const user: User = {
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

it("orders primary navigation and hides the new-task entry", () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AppShell user={user}>
          <div>content</div>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(screen.queryByText("MUA Test")).not.toBeInTheDocument();
  expect(screen.queryByText("AUTOMATION")).not.toBeInTheDocument();
  expect(screen.getByText("MUA")).toHaveClass("sidebar-brand-name");
  expect(screen.getByText("自动化测试平台")).toHaveClass("sidebar-brand-tag");
  expect(document.querySelector(".sidebar-logo-mark")).toBeInTheDocument();

  const navigation = screen.getByRole("navigation", { name: "主导航" });
  expect(within(navigation).queryByRole("link", { name: "新建任务" }))
    .not.toBeInTheDocument();
  expect(within(navigation).getAllByRole("link").map((link) =>
    link.textContent
  )).toEqual([
    "用例库",
    "测试计划",
    "测试报告",
    "执行记录",
    "设备池",
    "用户管理",
    "设置",
  ]);
});

it("hides administrator navigation entries for members", () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AppShell user={{ ...user, role: "member", username: "alice" }}>
          <div>content</div>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const navigation = screen.getByRole("navigation", { name: "主导航" });
  expect(within(navigation).getAllByRole("link").map((link) =>
    link.textContent
  )).toEqual([
    "用例库",
    "测试计划",
    "测试报告",
    "执行记录",
    "设备池",
    "设置",
  ]);
  expect(within(navigation).getByRole("link", { name: "设备池" }))
    .toHaveAttribute("href", "/pods");
  expect(within(navigation).queryByRole("link", { name: "用户管理" }))
    .not.toBeInTheDocument();
});
