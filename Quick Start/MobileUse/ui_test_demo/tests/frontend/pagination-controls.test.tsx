import { render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";

import { PaginationControls } from "../../web/components/pagination-controls";
import { user } from "./setup";

const STYLES = readFileSync("web/styles.css", "utf8");

it("opens the page-size menu downward inside an expanded card", () => {
  expect(STYLES).toMatch(
    /\.pagination-page-size \.single-select-menu\s*\{[^}]*left:\s*auto;[^}]*right:\s*0;[^}]*\}/s,
  );
  expect(STYLES).toMatch(
    /\.pagination-controls:has\(\s*\.pagination-page-size \.single-select-trigger\.open\s*\)\s*\{[^}]*padding-bottom:\s*7\.75rem;/s,
  );
  expect(STYLES).not.toMatch(
    /\.pagination-page-size \.single-select-menu\s*\{[^}]*(?:bottom:|top:)/s,
  );
});

it("renders totals and disables page boundaries", () => {
  render(
    <PaginationControls
      page={1}
      pageSize={10}
      total={25}
      onPageChange={() => undefined}
      onPageSizeChange={() => undefined}
    />,
  );

  expect(screen.getByText("共 25 条")).toBeVisible();
  expect(screen.getByText("第 1 / 3 页")).toBeVisible();
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled();
});

it("supports only 10, 20, and 50 and delegates reset to the size handler", async () => {
  const calls: string[] = [];
  render(
    <PaginationControls
      page={3}
      pageSize={10}
      total={80}
      onPageChange={(page) => calls.push(`page:${page}`)}
      onPageSizeChange={(pageSize) => calls.push(`size:${pageSize}`)}
    />,
  );

  await user.click(screen.getByRole("combobox", { name: "每页条数" }));
  const options = screen.getAllByRole("option");
  expect(options).toHaveLength(3);
  expect(options[0]).toHaveTextContent("10 条 / 页");
  expect(options[1]).toHaveTextContent("20 条 / 页");
  expect(options[2]).toHaveTextContent("50 条 / 页");
  await user.click(screen.getByRole("option", { name: "20 条 / 页" }));

  expect(calls).toEqual(["size:20"]);
});

it("handles empty totals and clamps pages beyond the end", async () => {
  const onPageChange = vi.fn();
  const { rerender } = render(
    <PaginationControls
      page={1}
      pageSize={10}
      total={0}
      onPageChange={onPageChange}
      onPageSizeChange={() => undefined}
    />,
  );

  expect(screen.getByText("第 1 / 1 页")).toBeVisible();
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();

  rerender(
    <PaginationControls
      page={9}
      pageSize={10}
      total={21}
      onPageChange={onPageChange}
      onPageSizeChange={() => undefined}
    />,
  );

  await waitFor(() => expect(onPageChange).toHaveBeenCalledWith(3));
  expect(screen.getByText("第 3 / 3 页")).toBeVisible();
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
});

it("does not repeat the same page correction when callback identity changes", async () => {
  const correction = vi.fn();
  const { rerender } = render(
    <PaginationControls
      page={9}
      pageSize={10}
      total={21}
      onPageChange={(page) => correction(page)}
      onPageSizeChange={() => undefined}
    />,
  );

  await waitFor(() => expect(correction).toHaveBeenCalledWith(3));
  rerender(
    <PaginationControls
      page={9}
      pageSize={10}
      total={21}
      onPageChange={(page) => correction(page)}
      onPageSizeChange={() => undefined}
    />,
  );

  await waitFor(() => expect(correction).toHaveBeenCalledTimes(1));
});
