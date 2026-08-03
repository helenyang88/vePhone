import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";

import { SingleSelect } from "../../web/components/single-select";
import { user } from "./setup";

const OPTIONS = [
  { value: "all", label: "全部状态" },
  { value: "running", label: "执行中" },
] as const;
const STYLES = readFileSync("web/styles.css", "utf8");

it("constrains long option lists to a scrollable menu", () => {
  expect(STYLES).toMatch(
    /\.single-select-option-list\s*\{[^}]*max-height:\s*280px;[^}]*overflow-y:\s*auto;[^}]*overscroll-behavior:\s*contain;/s,
  );
});

it("filters through an optional search input and shows an empty state", async () => {
  const onSearchChange = vi.fn();
  const { rerender } = render(
    <SingleSelect
      label="计划筛选"
      value="all"
      options={OPTIONS}
      onChange={() => undefined}
      searchValue=""
      onSearchChange={onSearchChange}
      searchLabel="搜索测试计划"
      emptyText="暂无匹配计划"
    />,
  );

  await user.click(screen.getByRole("combobox", { name: "计划筛选" }));
  const search = screen.getByRole("searchbox", { name: "搜索测试计划" });
  expect(search).toHaveAttribute("autocomplete", "off");
  expect(search).toHaveAttribute("placeholder", "搜索测试计划…");
  await user.type(search, "核心");
  expect(onSearchChange).toHaveBeenCalled();

  rerender(
    <SingleSelect
      label="计划筛选"
      value="all"
      options={[]}
      onChange={() => undefined}
      searchValue="核心"
      onSearchChange={onSearchChange}
      searchLabel="搜索测试计划"
      emptyText="暂无匹配计划"
    />,
  );
  expect(screen.getByText("暂无匹配计划")).toBeVisible();
});

it("selects an option and closes the popup", async () => {
  const onChange = vi.fn();
  render(
    <SingleSelect
      label="状态筛选"
      value="all"
      options={OPTIONS}
      onChange={onChange}
    />,
  );

  await user.click(screen.getByRole("combobox", { name: "状态筛选" }));
  expect(screen.getByRole("listbox", { name: "状态筛选选项" })).toBeVisible();
  await user.click(screen.getByRole("option", { name: "执行中" }));

  expect(onChange).toHaveBeenCalledWith("running");
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("closes with Escape without changing value", async () => {
  const onChange = vi.fn();
  render(
    <SingleSelect
      label="状态筛选"
      value="all"
      options={OPTIONS}
      onChange={onChange}
    />,
  );

  const trigger = screen.getByRole("combobox", { name: "状态筛选" });
  trigger.focus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("listbox", { name: "状态筛选选项" })).toBeVisible();
  await user.keyboard("{Escape}");

  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
  expect(trigger).toHaveFocus();
});

it("closes when Tab moves focus outside without restoring trigger focus", async () => {
  const onChange = vi.fn();
  render(
    <>
      <SingleSelect
        label="状态筛选"
        value="all"
        options={OPTIONS}
        onChange={onChange}
      />
      <button type="button">下一个控件</button>
    </>,
  );

  const trigger = screen.getByRole("combobox", { name: "状态筛选" });
  trigger.focus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("listbox", { name: "状态筛选选项" })).toBeVisible();

  await user.tab();

  expect(screen.getByRole("button", { name: "下一个控件" })).toHaveFocus();
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(trigger).not.toHaveFocus();
  expect(onChange).not.toHaveBeenCalled();
});

it("moves the active option with arrow keys and selects it with Enter", async () => {
  const onChange = vi.fn();
  render(
    <SingleSelect
      label="状态筛选"
      value="all"
      options={OPTIONS}
      onChange={onChange}
    />,
  );

  const trigger = screen.getByRole("combobox", { name: "状态筛选" });
  trigger.focus();
  await user.keyboard("{Enter}");

  const allOption = screen.getByRole("option", { name: "全部状态" });
  const runningOption = screen.getByRole("option", { name: "执行中" });
  expect(trigger).toHaveAttribute("aria-activedescendant", allOption.id);

  await user.keyboard("{ArrowDown}");
  expect(trigger).toHaveAttribute("aria-activedescendant", runningOption.id);
  expect(allOption).not.toHaveClass("active");
  expect(runningOption).toHaveClass("active");

  await user.keyboard("{ArrowUp}");
  expect(trigger).toHaveAttribute("aria-activedescendant", allOption.id);

  await user.keyboard("{ArrowDown}{Enter}");
  expect(onChange).toHaveBeenCalledWith("running");
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});
