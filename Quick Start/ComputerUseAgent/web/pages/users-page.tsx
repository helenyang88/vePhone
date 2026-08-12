import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { ApiError, api } from "../api/client";
import type {
  User,
  UserBatchCreate,
  UserListResponse,
  UserPasswordReset,
  UserUpdate,
} from "../api/types";
import { SingleSelect, type SelectOption } from "../components/single-select";
import { PageHeader } from "../components/page-header";

type UserRole = "admin" | "member";

type CreateRow = {
  id: string;
  username: string;
  display_name: string;
  email: string;
  password: string;
  role: UserRole;
};

const ROLE_OPTIONS: readonly SelectOption<UserRole>[] = [
  { value: "member", label: "成员" },
  { value: "admin", label: "管理员" },
];

function emptyRow(index = 1): CreateRow {
  return {
    id: `${Date.now()}-${index}`,
    username: "",
    display_name: "",
    email: "",
    password: "",
    role: "member",
  };
}

const REQUIRED_ROW_FIELDS: Array<keyof Pick<CreateRow, "username" | "password">> = [
  "username",
  "password",
];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [createRows, setCreateRows] = useState<CreateRow[]>([emptyRow(1)]);
  const [resetUser, setResetUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");

  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<User>("/auth/me"),
  });

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserListResponse>("/users"),
  });

  const createUsers = useMutation({
    mutationFn: (payload: UserBatchCreate) => api.post<UserListResponse>("/users/batch", payload),
    onSuccess: () => {
      setCreateRows([emptyRow(1)]);
      setMessage("用户已批量创建。");
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const updateUser = useMutation({
    mutationFn: ({ userId, payload }: { userId: number; payload: UserUpdate }) =>
      api.patch<User>(`/users/${userId}`, payload),
    onSuccess: () => {
      setMessage("用户角色已更新。");
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const setStatus = useMutation({
    mutationFn: ({ userId, action }: { userId: number; action: "enable" | "disable" }) =>
      api.post<User>(`/users/${userId}/${action}`),
    onSuccess: () => {
      setMessage("用户状态已更新。");
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const resetPassword = useMutation({
    mutationFn: ({ userId, payload }: { userId: number; payload: UserPasswordReset }) =>
      api.post<void>(`/users/${userId}/reset-password`, payload),
    onSuccess: () => {
      setResetUser(null);
      setNewPassword("");
      setConfirmPassword("");
      setMessage("密码已重置。");
    },
  });

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    const rows = validCreateRows();
    if (rows.length === 0) {
      setMessage("请至少补齐一行用户信息。");
      return;
    }
    createUsers.mutate({
      users: rows.map((row) => ({
        username: row.username.trim(),
        display_name: row.display_name.trim() || null,
        email: row.email.trim() || null,
        password: row.password,
        role: row.role,
      })),
    });
  }

  function validCreateRows() {
    return createRows.filter((row) =>
      REQUIRED_ROW_FIELDS.every((field) => row[field].trim().length > 0)
    );
  }

  function updateCreateRow(
    rowId: string,
    patch: Partial<CreateRow>,
  ) {
    setCreateRows((current) =>
      current.map((row) => row.id === rowId ? { ...row, ...patch } : row)
    );
  }

  function addCreateRow() {
    setCreateRows((current) => [...current, emptyRow(current.length + 1)]);
  }

  function removeCreateRow(rowId: string) {
    setCreateRows((current) =>
      current.length === 1 ? current : current.filter((row) => row.id !== rowId)
    );
  }

  function submitReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resetUser) return;
    setMessage("");
    resetPassword.mutate({
      userId: resetUser.id,
      payload: {
        new_password: newPassword,
        confirm_password: confirmPassword,
      },
    });
  }

  const validRows = validCreateRows();
  const invalidRowCount = createRows.length - validRows.length;
  const adminDraftCount = createRows.filter((row) => row.role === "admin").length;
  const memberDraftCount = createRows.length - adminDraftCount;
  const error = createUsers.error || updateUser.error || setStatus.error || resetPassword.error || users.error;

  return (
    <div className="settings-page">
      <PageHeader
        breadcrumbs={[{ label: "首页", to: "/tasks" }, { label: "用户管理" }]}
        title="用户管理"
        description="创建员工账号、启用或停用账号，并为员工重置密码。"
      />

      <div className="settings-card">
        <section className="settings-section">
          <div className="section-title-row user-batch-header">
            <div>
              <h2>批量创建员工账号</h2>
              <p className="section-desc">支持逐行录入员工信息，确认无误后一次性创建账号。</p>
            </div>
            <div className="table-actions user-batch-actions">
              <button type="button" className="secondary-button user-batch-action" onClick={addCreateRow}>
                添加一行
              </button>
              <button
                type="submit"
                form="batch-create-users"
                className="primary-button user-batch-action"
                disabled={createUsers.isPending}
              >
                批量创建用户
              </button>
            </div>
          </div>
          <form id="batch-create-users" onSubmit={submitCreate}>
            <div className="user-batch-summary">
              <span>{validRows.length} 行可提交，{invalidRowCount} 行需补充</span>
              <div className="user-batch-stats compact">
                <span><strong>{validRows.length}</strong>可创建</span>
                <span><strong>{memberDraftCount}</strong>成员</span>
                <span><strong>{adminDraftCount}</strong>管理员</span>
              </div>
            </div>
            <div className="user-batch-layout">
              <div className="user-batch-table-wrap">
                <div className="user-batch-scroll">
                  <table className="data-table user-batch-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>用户名</th>
                        <th>显示名称</th>
                        <th>邮箱</th>
                        <th>初始密码</th>
                        <th>角色</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {createRows.map((row, index) => (
                        <tr key={row.id}>
                          <td className="muted mono">{String(index + 1).padStart(2, "0")}</td>
                          <td>
                            <input
                              aria-label={`用户名 ${index + 1}`}
                              className="table-input"
                              value={row.username}
                              onChange={(event) => updateCreateRow(row.id, { username: event.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              aria-label={`显示名称 ${index + 1}`}
                              className="table-input"
                              value={row.display_name}
                              onChange={(event) => updateCreateRow(row.id, { display_name: event.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              aria-label={`邮箱 ${index + 1}`}
                              className="table-input"
                              value={row.email}
                              onChange={(event) => updateCreateRow(row.id, { email: event.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              aria-label={`初始密码 ${index + 1}`}
                              className="table-input"
                              type="password"
                              value={row.password}
                              onChange={(event) => updateCreateRow(row.id, { password: event.target.value })}
                            />
                          </td>
                          <td>
                            <SingleSelect
                              label={`角色 ${index + 1}`}
                              value={row.role}
                              options={ROLE_OPTIONS}
                              onChange={(role) => updateCreateRow(row.id, { role })}
                              className="user-role-select"
                            />
                          </td>
                          <td>
                            <button
                              type="button"
                              className="secondary-button compact"
                              onClick={() => removeCreateRow(row.id)}
                              disabled={createRows.length === 1}
                            >
                              删除
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </form>
        </section>

        <section className="settings-section">
          <div className="section-title-row">
            <div>
              <h2>用户列表</h2>
              <p className="section-desc">停用用户后，该用户不能再登录，已有会话也会失效。</p>
            </div>
          </div>
          {users.isLoading ? (
            <p className="muted">加载中...</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>用户名</th>
                    <th>显示名称</th>
                    <th>邮箱</th>
                    <th>角色</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {(users.data?.items ?? []).map((item) => (
                    <tr key={item.id}>
                      <td>{item.username}</td>
                      <td>{item.display_name || "-"}</td>
                      <td>{item.email || "-"}</td>
                      <td>
                        <SingleSelect
                          label={`${item.username} 角色`}
                          value={item.role}
                          options={ROLE_OPTIONS}
                          disabled={item.id === me.data?.id}
                          onChange={(role) => updateUser.mutate({
                            userId: item.id,
                            payload: { role },
                          })}
                          className="user-role-select"
                        />
                      </td>
                      <td>{item.status === "active" ? "启用" : "停用"}</td>
                      <td>
                        <div className="table-actions">
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => setResetUser(item)}
                          >
                            重置密码
                          </button>
                          {item.status === "active" ? (
                            <button
                              type="button"
                              className="secondary-button danger"
                              onClick={() =>
                                setStatus.mutate({ userId: item.id, action: "disable" })}
                            >
                              停用
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                setStatus.mutate({ userId: item.id, action: "enable" })}
                            >
                              启用
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {resetUser && (
        <div className="modal-overlay" role="presentation">
          <form className="modal-panel confirm-dialog-panel" onSubmit={submitReset}>
            <div className="modal-header">
              <div>
                <h3>重置密码</h3>
                <p className="confirm-dialog-description">
                  为用户 {resetUser.username} 设置新密码。
                </p>
              </div>
              <button
                type="button"
                className="modal-close"
                aria-label="关闭"
                onClick={() => setResetUser(null)}
              >
                ×
              </button>
            </div>
            <div className="modal-body user-reset-modal-body">
              <div className="user-reset-fields">
                <div className="settings-field">
                  <label htmlFor="reset-password">新密码</label>
                  <input
                    id="reset-password"
                    type="password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    autoComplete="new-password"
                  />
                </div>
                <div className="settings-field">
                  <label htmlFor="reset-confirm-password">确认新密码</label>
                  <input
                    id="reset-confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    autoComplete="new-password"
                  />
                </div>
              </div>
              <p className="modal-case-title user-reset-tip">
                保存后该用户的已有会话会失效，需要使用新密码重新登录。
              </p>
            </div>
            <div className="modal-footer">
              <button type="button" className="secondary-button" onClick={() => setResetUser(null)}>
                取消
              </button>
              <button type="submit" className="primary-button" disabled={resetPassword.isPending}>
                确认重置
              </button>
            </div>
          </form>
        </div>
      )}

      <div aria-live="polite" className="settings-feedback">
        {message && <p className="success-message">{message}</p>}
        {error && (
          <div className="form-feedback error" role="alert">
            <p>{error instanceof ApiError ? error.message : "请求失败"}</p>
          </div>
        )}
      </div>
    </div>
  );
}
