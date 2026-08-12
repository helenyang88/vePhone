import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "../api/client";
import type { Credentials, User } from "../api/types";

function BrandLogo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10 2v7.31M14 9.3V1.99M8.5 2h7M14 9.3a6.5 6.5 0 1 1-4 0" />
    </svg>
  );
}

function FeatureIcon({ d }: { d: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="20" height="16" x="2" y="4" rx="2" /><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61M2 2l20 20" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  );
}

const FEATURES = [
  { icon: "M4 19.5V5a2 2 0 0 1 2-2h11a1 1 0 0 1 1 1v16a1 1 0 0 0-1-1H6a2 2 0 0 0-2 2M8 7h6M8 11h7M8 15h4", text: "用例库与测试计划统一维护" },
  { icon: "M3 4h18v12H3zM8 20h8M12 16v4", text: "Computer Use 桌面执行链路" },
  { icon: "M3 3v18h18M7 15l4-4 3 3 5-7", text: "Trace、截图与结构化结果沉淀" },
];

export function LoginPage({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const mutation = useMutation({
    mutationFn: (credentials: Credentials) =>
      api.post<User>("/auth/login", credentials),
    onSuccess: onAuthenticated,
  });

  function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    mutation.mutate({ username, password });
  }

  const error = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <main className="auth-split">
      <div className="auth-brand">
        <div className="auth-brand-inner">
          <div className="auth-brand-top">
            <div className="auth-brand-logo">
              <BrandLogo />
            </div>
            <div>
              <div className="auth-brand-name">CUA Test</div>
              <span className="auth-brand-tag">Computer Use automation</span>
            </div>
          </div>
        </div>

        <div className="auth-brand-inner">
          <h1 className="auth-brand-h1">
            <span className="auth-title-primary">让电脑桌面自动化测试</span><br />
            <span className="gradient">更可追踪</span>
          </h1>
          <p className="auth-brand-desc">
            围绕用例、测试计划、CUA 节点执行和报告沉淀，统一管理电脑桌面自动化测试流程。
          </p>

          <div className="auth-features">
            {FEATURES.map((f, i) => (
              <div className="auth-feature" key={i}>
                <div className="auth-feature-icon">
                  <FeatureIcon d={f.icon} />
                </div>
                <div className="auth-feature-text">{f.text}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="auth-brand-inner">
          <div className="auth-brand-bottom">
            <div className="auth-brand-dots">
              <span /><span /><span />
            </div>
            <div className="auth-brand-line" />
          </div>
        </div>
      </div>

      <div className="auth-form-panel">
        <div className="auth-mobile-logo">
          <div className="auth-mobile-logo-logo">
            <BrandLogo />
          </div>
          <span>CUA Test</span>
        </div>

        <div className="auth-card">
          <div className="auth-heading">
            <h2>欢迎回来</h2>
            <p>登录你的 CUA Test 账号</p>
          </div>

          <form onSubmit={submit}>
            <div className="form-field">
              <label htmlFor="login-username">用户名</label>
              <div className="input-with-icon-right">
                <span className="left-icon"><MailIcon /></span>
                <input
                  id="login-username"
                  autoComplete="username"
                  required
                  minLength={3}
                  placeholder="输入用户名"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </div>
            </div>

            <div className="form-field">
              <label htmlFor="login-password">密码</label>
              <div className="input-with-icon-right">
                <span className="left-icon"><LockIcon /></span>
                <input
                  id="login-password"
                  autoComplete="current-password"
                  required
                  minLength={12}
                  type={showPassword ? "text" : "password"}
                  placeholder="输入密码"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  type="button"
                  className="right-btn"
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  <EyeIcon open={showPassword} />
                </button>
              </div>
            </div>

            <div className="form-row">
              <label className="checkbox-label">
                <input type="checkbox" />
                记住我
              </label>
            </div>

            {error && (
              <div className="form-feedback error" role="alert">
                {error.message}
                {error.requestId && <small>诊断标识：{error.requestId}</small>}
              </div>
            )}

            <button className="primary-button block" disabled={mutation.isPending} type="submit">
              {mutation.isPending ? "登录中..." : "登录"}
              {!mutation.isPending && <ArrowRightIcon />}
            </button>
          </form>

          <div className="auth-footer">
            <p>还没有账号？<a href="#">联系管理员开通</a></p>
          </div>
        </div>

      </div>
    </main>
  );
}
