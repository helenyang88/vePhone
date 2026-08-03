import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { ApiError, api } from "../api/client";
import type { Credentials, User } from "../api/types";

function BrandLogo() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10 2v7.31M14 9.3V1.99M8.5 2h7M14 9.3a6.5 6.5 0 1 1-4 0" />
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

function UserIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
    </svg>
  );
}

export function SetupPage({
  onAlreadyInitialized,
  onAuthenticated,
}: {
  onAlreadyInitialized: () => void;
  onAuthenticated: (user: User) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const mutation = useMutation({
    mutationFn: (credentials: Credentials) =>
      api.post<User>("/setup/admin", credentials),
    onSuccess: onAuthenticated,
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        onAlreadyInitialized();
      }
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate({ username, password });
  }

  const error = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <main className="setup-page">
      <div className="setup-card">
        <div style={{ display: "flex", justifyContent: "center", marginBottom: "1.5rem" }}>
          <div style={{
            width: "48px", height: "48px", borderRadius: "12px",
            background: "linear-gradient(135deg, #6366f1, #4f46e5)",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 4px 12px rgba(79,70,229,0.35)",
          }}>
            <BrandLogo />
          </div>
        </div>

        <div style={{ textAlign: "center", marginBottom: "1.75rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>首次使用</p>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "0.5rem" }}>初始化管理员</h1>
          <p className="muted">创建唯一的本地管理员账号，密码不会保存在浏览器中。</p>
        </div>

        <form onSubmit={submit} className="form-stack">
          <div className="form-field">
            <label htmlFor="setup-username">用户名</label>
            <div className="input-with-icon-right">
              <span className="left-icon"><UserIcon /></span>
              <input
                id="setup-username"
                autoComplete="username"
                minLength={3}
                maxLength={64}
                required
                placeholder="输入用户名（至少3个字符）"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </div>
          </div>

          <div className="form-field">
            <label htmlFor="setup-password">密码</label>
            <div className="input-with-icon-right">
              <span className="left-icon"><LockIcon /></span>
              <input
                id="setup-password"
                autoComplete="new-password"
                minLength={12}
                maxLength={128}
                required
                type="password"
                placeholder="输入密码（至少12个字符）"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
          </div>

          {error && (
            <div className="form-feedback error" role="alert">
              {error.message}
            </div>
          )}

          <button className="primary-button block" disabled={mutation.isPending} type="submit">
            {mutation.isPending ? "创建中..." : "创建管理员"}
          </button>
        </form>
      </div>
    </main>
  );
}
