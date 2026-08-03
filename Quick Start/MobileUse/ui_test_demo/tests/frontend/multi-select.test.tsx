/// <reference types="node" />

import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import {
  MultiSelect,
  type MultiSelectOption,
} from "../../web/components/multi-select";
import { user } from "./setup";

const STYLES = readFileSync("web/styles.css", "utf8");

const OPTIONS: MultiSelectOption[] = [
  {
    value: "P0",
    label: "P0",
    count: 9,
    foregroundColor: "#94600F",
    backgroundColor: "#94600F1A",
  },
  {
    value: "smoke",
    label: "smoke",
    count: 4,
    foregroundColor: "#0F766E",
    backgroundColor: "#0F766E1A",
  },
];

it("matches SingleSelect and supports keyboard multi-selection", async () => {
  const onChange = vi.fn();
  render(
    <MultiSelect
      label="标签"
      values={[]}
      options={OPTIONS}
      onChange={onChange}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  const trigger = screen.getByRole("combobox", { name: "标签" });
  expect(trigger).toHaveClass("single-select-trigger");
  expect(trigger).toHaveTextContent("全部标签");

  await user.click(trigger);
  const listbox = screen.getByRole("listbox", { name: "标签选项" });
  expect(listbox).toHaveAttribute("aria-multiselectable", "true");

  await user.keyboard("{ArrowDown}{Space}");
  expect(onChange).toHaveBeenCalledWith(["smoke"]);
  expect(screen.getByRole("listbox")).toBeVisible();
});

it("uses registered transparent colors without borders or shadows", async () => {
  render(
    <MultiSelect
      label="标签"
      values={["P0"]}
      options={OPTIONS}
      onChange={() => undefined}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  const trigger = screen.getByRole("combobox", { name: "标签" });
  expect(trigger).toHaveTextContent("标签（1）");
  await user.click(trigger);

  const selected = screen.getByRole("option", { name: /P0/ });
  expect(selected).toHaveStyle({
    border: "0",
    backgroundColor: OPTIONS[0].backgroundColor,
    color: OPTIONS[0].foregroundColor,
    boxShadow: "none",
  });
  expect(selected.querySelector("svg path")).toHaveAttribute(
    "stroke-linecap",
    "round",
  );
  expect(selected.querySelector("svg path")).toHaveAttribute(
    "stroke-linejoin",
    "round",
  );
});

it("closes with Escape, blur, and outside click", async () => {
  render(
    <>
      <MultiSelect
        label="标签"
        values={[]}
        options={OPTIONS}
        onChange={() => undefined}
        searchValue=""
        onSearchChange={() => undefined}
      />
      <button type="button">外部控件</button>
    </>,
  );

  const trigger = screen.getByRole("combobox", { name: "标签" });
  trigger.focus();
  await user.keyboard("{Enter}");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();

  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "外部控件" }));
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

  await user.click(trigger);
  const external = screen.getByRole("button", { name: "外部控件" });
  fireEvent.blur(trigger, { relatedTarget: external });
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("closes with Escape while the search input has focus", async () => {
  render(
    <MultiSelect
      label="标签"
      values={[]}
      options={OPTIONS}
      onChange={() => undefined}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  const trigger = screen.getByRole("combobox", { name: "标签" });
  await user.click(trigger);
  const search = screen.getByRole("searchbox", { name: "搜索标签" });
  search.focus();
  await user.keyboard("{Escape}");

  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("navigates and selects options while the search input has focus", async () => {
  const onChange = vi.fn();
  render(
    <MultiSelect
      label="标签"
      values={[]}
      options={OPTIONS}
      onChange={onChange}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  await user.click(screen.getByRole("combobox", { name: "标签" }));
  const search = screen.getByRole("searchbox", { name: "搜索标签" });
  const smoke = screen.getByRole("option", { name: /smoke/ });
  search.focus();

  await user.keyboard("{ArrowUp}");
  expect(search).toHaveAttribute("aria-activedescendant", smoke.id);
  await user.keyboard("{ArrowDown}");
  await user.keyboard("{ArrowDown}");
  expect(search).toHaveAttribute("aria-controls");
  expect(search).toHaveAttribute("aria-activedescendant", smoke.id);

  await user.keyboard("{Enter}");
  expect(onChange).toHaveBeenCalledWith(["smoke"]);
  expect(screen.getByRole("listbox")).toBeVisible();
});

it("keeps consecutive selections and removals synchronized", async () => {
  const onChange = vi.fn();

  function Harness() {
    const [values, setValues] = useState<string[]>([]);
    return (
      <MultiSelect
        label="标签"
        values={values}
        options={OPTIONS}
        onChange={(next) => {
          onChange(next);
          setValues(next);
        }}
        searchValue=""
        onSearchChange={() => undefined}
      />
    );
  }

  render(<Harness />);
  const trigger = screen.getByRole("combobox", { name: "标签" });
  trigger.focus();
  await user.keyboard("{Enter}{Space}{ArrowDown}{Space}");

  expect(onChange).toHaveBeenNthCalledWith(1, ["P0"]);
  expect(onChange).toHaveBeenNthCalledWith(2, ["P0", "smoke"]);
  expect(trigger).toHaveTextContent("标签（2）");

  await user.keyboard("{ArrowUp}{Space}{ArrowDown}{Space}");
  expect(onChange).toHaveBeenNthCalledWith(3, ["smoke"]);
  expect(onChange).toHaveBeenNthCalledWith(4, []);
  expect(trigger).toHaveTextContent("全部标签");
});

it("accumulates toggles before parent values synchronize", () => {
  const onChange = vi.fn();
  render(
    <MultiSelect
      label="标签"
      values={[]}
      options={OPTIONS}
      onChange={onChange}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  const trigger = screen.getByRole("combobox", { name: "标签" });
  fireEvent.keyDown(trigger, { key: "Enter" });
  fireEvent.keyDown(trigger, { key: " " });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  fireEvent.keyDown(trigger, { key: " " });

  expect(onChange).toHaveBeenNthCalledWith(1, ["P0"]);
  expect(onChange).toHaveBeenNthCalledWith(2, ["P0", "smoke"]);
});

it("rolls back the optimistic draft when the parent supplies new values", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <MultiSelect
      label="标签"
      values={[]}
      options={OPTIONS}
      onChange={onChange}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  const trigger = screen.getByRole("combobox", { name: "标签" });
  await user.click(trigger);
  await user.click(screen.getByRole("option", { name: /P0/ }));
  expect(trigger).toHaveTextContent("标签（1）");
  expect(screen.getByRole("option", { name: /P0/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  rerender(
    <MultiSelect
      label="标签"
      values={[]}
      options={OPTIONS}
      onChange={onChange}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  expect(trigger).toHaveTextContent("全部标签");
  expect(screen.getByRole("option", { name: /P0/ })).toHaveAttribute(
    "aria-selected",
    "false",
  );
});

it("keeps a visible active outline on selected keyboard options", async () => {
  render(
    <MultiSelect
      label="标签"
      values={["P0"]}
      options={OPTIONS}
      onChange={() => undefined}
      searchValue=""
      onSearchChange={() => undefined}
    />,
  );

  await user.click(screen.getByRole("combobox", { name: "标签" }));
  const selectedActive = screen.getByRole("option", { name: /P0/ });

  expect(selectedActive).toHaveClass("selected", "active");
  expect(STYLES).toMatch(
    /\.multi-select-option\.selected\.active\s*\{[^}]*outline:\s*2px\s+solid/s,
  );
});

it("filters options and confirms the controlled selection", async () => {
  const onConfirm = vi.fn();

  function Harness() {
    const [values, setValues] = useState<string[]>([]);
    const [search, setSearch] = useState("");
    return (
      <MultiSelect
        label="标签"
        values={values}
        options={OPTIONS.filter((option) => option.label.includes(search))}
        onChange={setValues}
        onConfirm={onConfirm}
        searchValue={search}
        onSearchChange={setSearch}
      />
    );
  }

  render(<Harness />);
  await user.click(screen.getByRole("combobox", { name: "标签" }));
  await user.type(screen.getByRole("searchbox", { name: "搜索标签" }), "P0");
  expect(screen.queryByRole("option", { name: /smoke/ })).not.toBeInTheDocument();
  await user.click(screen.getByRole("option", { name: /P0/ }));
  await user.click(screen.getByRole("button", { name: "确认标签选择" }));

  expect(onConfirm).toHaveBeenCalledWith(["P0"]);
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});
