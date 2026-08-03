import { useCallback, useEffect, useId, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type { PodStreamSession } from "../api/types";

type StreamStatus = "idle" | "starting" | "connected" | "closing";

type VePhoneInstance = {
  start(options: Record<string, unknown>): Promise<unknown>;
  stop(): Promise<unknown>;
  destroy(): Promise<unknown>;
};

function isPCBrowser(): boolean {
  return !/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent,
  );
}

export function CloudPhoneStreamPanel({ podId }: { podId: string }) {
  const rawDomId = useId();
  const domId = `cloud-phone-player-${rawDomId.replace(/[^A-Za-z0-9_-]/g, "")}`;
  const sdkRef = useRef<VePhoneInstance | null>(null);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  const release = useCallback(async () => {
    const sdk = sdkRef.current;
    sdkRef.current = null;
    if (!sdk) return;
    setStatus("closing");
    try {
      await sdk.stop();
    } finally {
      await sdk.destroy();
      setFullscreen(false);
      setStatus("idle");
    }
  }, []);

  useEffect(() => () => {
    void release();
  }, [release]);

  async function startStream() {
    if (status !== "idle") return;
    setError(null);
    setStatus("starting");
    try {
      const session = await api.post<PodStreamSession>(`/pod-pool/${podId}/stream-session`);
      const { default: VePhoneSDK } = await import("@volcengine/vephone");
      const sdk = new VePhoneSDK({
        userId: session.user_id,
        accountId: session.account_id,
        domId,
        isPC: isPCBrowser(),
        isDebug: import.meta.env.DEV,
        enableLocalKeyboard: false,
        enableSyncClipboard: false,
        enableLocalMouseScroll: true,
      }) as VePhoneInstance;
      sdkRef.current = sdk;
      await sdk.start({
        productId: session.product_id,
        podId: session.pod_id,
        token: session.token,
        rotation: "portrait",
        mute: true,
        audioAutoPlay: true,
      });
      setStatus("connected");
    } catch (err) {
      if (sdkRef.current) {
        await release();
      } else {
        setStatus("idle");
      }
      setError(err instanceof ApiError ? err.message : "实时画面连接失败");
    }
  }

  const connected = status === "connected";
  const busy = status === "starting" || status === "closing";

  return (
    <section
      className={`cloud-phone-stream-panel${fullscreen ? " cloud-phone-stream-fullscreen" : ""}`}
      aria-label="云手机实时画面"
    >
      <div className="cloud-phone-stream-header">
        <div>
          <h4>实时画面</h4>
          <p>用于查看当前云手机实例的推流画面，关闭弹窗时会自动断开连接。</p>
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
              onClick={() => void release()}
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
            disabled={busy}
          >
            {status === "starting" ? "连接中..." : "查看画面"}
          </button>
        )}
      </div>
      {error && <p className="form-error">{error}</p>}
      {connected && <p className="stream-status-text">实时画面已连接</p>}
      <div id={domId} className="cloud-phone-player" />
    </section>
  );
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
