import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { CloudPhoneStreamPanel } from "../../web/components/cloud-phone-stream-panel";
import { server, user } from "./setup";

describe("CloudPhoneStreamPanel", () => {
  it("默认内嵌 proxy_viewer_url，并保留新窗口兜底", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue({} as Window);
    server.use(
      http.post("/api/v1/pod-pool/i-node/stream-session", () =>
        HttpResponse.json({
          proxy_viewer_url: "/novnc/view?sid=proxy",
          viewer_url: "https://example.com/novnc/view?sid=https",
          websocket_url: "wss://example.com/novnc/ws?sid=https",
          http_viewer_url: "http://example.com/novnc/view?sid=http",
          ws_websocket_url: "ws://example.com/novnc/ws?sid=http",
          expires_at: 1786538614,
        }),
      ),
    );

    render(<CloudPhoneStreamPanel podId="i-node" />);

    await user.click(screen.getByRole("button", { name: "查看画面" }));

    expect(await screen.findByTitle("CUA noVNC 实时画面"))
      .toHaveAttribute("src", "/novnc/view?sid=proxy");
    expect(screen.getByText("实时画面已连接")).toBeVisible();
    expect(open).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "新窗口打开" }));

    expect(open).toHaveBeenCalledWith(
      "/novnc/view?sid=proxy",
      "_blank",
      "noopener,noreferrer",
    );
  });
});
