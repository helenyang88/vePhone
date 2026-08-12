import { useState } from "react";

import { ApiError, api } from "../api/client";
import type { PodStreamSession } from "../api/types";

type StreamStatus = "idle" | "starting" | "connected" | "closing";

export function CloudPhoneStreamPanel({
  podId,
  disabledReason,
}: {
  podId: string;
  disabledReason?: string | null;
}) {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);

  function release() {
    setStatus("closing");
    setViewerUrl(null);
    setFullscreen(false);
    setStatus("idle");
  }

  function openInNewWindow() {
    if (!viewerUrl) return;
    const opened = window.open(viewerUrl, "_blank", "noopener,noreferrer");
    if (!opened) setError("浏览器阻止了新窗口，请允许弹窗后重试");
  }

  async function startStream() {
    if (disabledReason) return;
    if (status !== "idle") return;
    setError(null);
    setStatus("starting");
    try {
      const session = await api.post<PodStreamSession>(`/pod-pool/${podId}/stream-session`);
      const url = session.proxy_viewer_url || viewerUrlForPage(session);
      if (!url) throw new Error("novnc_url_missing");
      setViewerUrl(url);
      setStatus("connected");
    } catch (err) {
      setStatus("idle");
      setError(
        err instanceof ApiError
          ? err.message
          : "实时画面连接失败",
      );
    }
  }

  const connected = status === "connected";
  const busy = status === "starting" || status === "closing";

  return (
    <section
      className={`cloud-phone-stream-panel${fullscreen ? " cloud-phone-stream-fullscreen" : ""}`}
      aria-label="CUA noVNC 实时画面"
    >
      <div className="cloud-phone-stream-header">
        <div>
          <h4>实时画面</h4>
          <p>用于查看当前 CUA 节点的 noVNC 桌面画面，关闭弹窗时会自动断开连接。</p>
        </div>
        {connected ? (
          <div className="cloud-phone-stream-actions">
            <button
              type="button"
              className="icon-button cloud-phone-fullscreen-button"
              onClick={() => setFullscreen((value) => !value)}
              aria-label={fullscreen ? "退出全屏" : "放大实时画面"}
              title={fullscreen ? "退出全屏" : "放大实时画面"}
            >
              {fullscreen ? <ExitFullscreenIcon /> : <FullscreenIcon />}
            </button>
            <button
              type="button"
              className="secondary-button compact"
              onClick={openInNewWindow}
              disabled={busy || !viewerUrl}
            >
              新窗口打开
            </button>
            <button
              type="button"
              className="secondary-button compact"
              onClick={release}
              disabled={busy}
            >
              关闭画面
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="primary-button compact"
            onClick={() => void startStream()}
            disabled={busy || Boolean(disabledReason)}
          >
            {status === "starting" ? "连接中..." : "查看画面"}
          </button>
        )}
      </div>
      {error && <p className="form-error">{error}</p>}
      {disabledReason && <p className="form-error">{disabledReason}</p>}
      {connected && <p className="stream-status-text">实时画面已连接</p>}
      {viewerUrl && (
        <iframe
          className="cloud-phone-player"
          title="CUA noVNC 实时画面"
          src={viewerUrl}
          sandbox="allow-scripts allow-same-origin allow-forms allow-pointer-lock"
        />
      )}
    </section>
  );
}

function viewerUrlForPage(session: PodStreamSession): string | null {
  if (window.location.protocol === "http:") {
    return session.http_viewer_url || session.viewer_url;
  }
  return session.viewer_url || session.http_viewer_url;
}

function FullscreenIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 3H3v5" />
      <path d="M16 3h5v5" />
      <path d="M21 16v5h-5" />
      <path d="M3 16v5h5" />
    </svg>
  );
}

function ExitFullscreenIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 3v5H3" />
      <path d="M16 3v5h5" />
      <path d="M21 16h-5v5" />
      <path d="M3 16h5v5" />
    </svg>
  );
}
