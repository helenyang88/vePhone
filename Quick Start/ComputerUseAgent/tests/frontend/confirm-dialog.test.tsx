import { render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";

import { ConfirmDialog } from "../../web/components/confirm-dialog";
import { user } from "./setup";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <div className="app-shell" data-testid="app-shell">
      <button type="button" onClick={() => setOpen(true)}>打开</button>
      <ConfirmDialog
        open={open}
        title="删除测试计划"
        description="确认删除"
        confirmLabel="确认删除"
        pendingLabel="正在删除…"
        onClose={() => setOpen(false)}
        onConfirm={() => undefined}
      />
    </div>
  );
}

it("traps focus, inerts the background, and restores the opener", async () => {
  render(<Harness />);
  const opener = screen.getByRole("button", { name: "打开" });
  await user.click(opener);

  const shell = screen.getByTestId("app-shell");
  const dialog = screen.getByRole("dialog", { name: "删除测试计划" });
  const cancel = screen.getByRole("button", { name: "取消" });
  const confirm = screen.getByRole("button", { name: "确认删除" });
  expect(shell).not.toContainElement(dialog);
  expect(shell).toHaveAttribute("inert");
  expect(cancel).toHaveFocus();

  await user.tab({ shift: true });
  expect(confirm).toHaveFocus();
  await user.tab();
  expect(cancel).toHaveFocus();

  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(shell).not.toHaveAttribute("inert");
  expect(opener).toHaveFocus();
});
