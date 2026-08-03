import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router";

import { ApiError, api } from "../api/client";
import type {
  RunnerSettingsUpdate,
  SettingsResponse,
  User,
} from "../api/types";
import { PageHeader } from "../components/page-header";
import {
  getStoredThemePreference,
  saveThemePreference,
  type ThemePreference,
} from "../utils/theme";

type MobileField =
  | "access_key_id"
  | "secret_access_key"
  | "product_id"
  | "account_id"
  | "sts_role_trn"
  | "stream_token_ttl_seconds"
  | "tos_bucket"
  | "tos_endpoint"
  | "tos_region"
  | "use_base64_screenshot"
  | "max_step"
  | "timeout_seconds"
  | "callback_info"
  | "output_schema"
  | "retry_limit"
  | "system_prompt"
  | "screen_record"
  | "mcp_json"
  | "max_output_tokens"
  | "gps_info";

type MobileValues = Record<MobileField, string>;
type FieldErrors = Partial<Record<MobileField, string>>;

const EMPTY_VALUES: MobileValues = {
  access_key_id: "",
  secret_access_key: "",
  product_id: "",
  account_id: "",
  sts_role_trn: "",
  stream_token_ttl_seconds: "600",
  tos_bucket: "",
  tos_endpoint: "",
  tos_region: "",
  use_base64_screenshot: "false",
  max_step: "100",
  timeout_seconds: "120",
  callback_info: "",
  output_schema: "",
  retry_limit: "3",
  system_prompt: "",
  screen_record: "false",
  mcp_json: "",
  max_output_tokens: "",
  gps_info: "",
};

const FIELD_LABELS: Record<MobileField, string> = {
  access_key_id: "Access Key ID",
  secret_access_key: "Secret Access Key",
  product_id: "Product ID",
  account_id: "Volcengine AccountId",
  sts_role_trn: "STS RoleTrn",
  stream_token_ttl_seconds: "推流 Token 有效期（秒）",
  tos_bucket: "TOS Bucket",
  tos_endpoint: "TOS Endpoint",
  tos_region: "TOS Region",
  use_base64_screenshot: "UseBase64Screenshot",
  max_step: "MaxStep",
  timeout_seconds: "默认任务超时 Timeout（秒）",
  callback_info: "CallbackInfo",
  output_schema: "OutputSchema",
  retry_limit: "RetryLimit",
  system_prompt: "SystemPrompt",
  screen_record: "IsScreenRecord",
  mcp_json: "McpJson",
  max_output_tokens: "MaxOutputTokens",
  gps_info: "GpsInfo",
};

const REQUIRED_FIELDS: MobileField[] = [
  "access_key_id",
  "secret_access_key",
  "product_id",
  "tos_bucket",
  "tos_region",
];

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </svg>
  );
}

function MonitorIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="20" height="14" x="2" y="3" rx="2" /><line x1="8" x2="16" y1="21" y2="21" /><line x1="12" x2="12" y1="17" y2="21" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function SlidersIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="4" x2="4" y1="21" y2="14" /><line x1="4" x2="4" y1="10" y2="3" /><line x1="12" x2="12" y1="21" y2="12" /><line x1="12" x2="12" y1="8" y2="3" /><line x1="20" x2="20" y1="21" y2="16" /><line x1="20" x2="20" y1="12" y2="3" /><line x1="1" x2="7" y1="14" y2="14" /><line x1="9" x2="15" y1="8" y2="8" /><line x1="17" x2="23" y1="16" y2="16" />
    </svg>
  );
}

function RequestId({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <p className="request-id">
      request_id：<code>{value}</code>
    </p>
  );
}

function initials(name: string) {
  const trimmed = name.trim();
  return trimmed ? trimmed.slice(0, 2).toUpperCase() : "MU";
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<MobileValues>(EMPTY_VALUES);
  const [dirtyFields, setDirtyFields] = useState<Set<MobileField>>(new Set());
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [localError, setLocalError] = useState("");
  const [saved, setSaved] = useState(false);
  const [profileName, setProfileName] = useState("管理员");
  const [profileEmail, setProfileEmail] = useState("admin@example.com");
  const [theme, setTheme] = useState<ThemePreference>(() => getStoredThemePreference());
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");

  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<User>("/auth/me"),
  });
  const isAdmin = me.data?.role === "admin";
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsResponse>("/settings"),
    enabled: isAdmin,
  });

  useEffect(() => {
    if (!settings.data) return;
    setValues({
      ...EMPTY_VALUES,
      product_id: settings.data.mobile_use.product_id ?? "",
      account_id: settings.data.mobile_use.account_id ?? "",
      sts_role_trn: settings.data.mobile_use.sts_role_trn ?? "",
      stream_token_ttl_seconds: String(settings.data.mobile_use.stream_token_ttl_seconds),
      tos_bucket: settings.data.mobile_use.tos_bucket ?? "",
      tos_endpoint: settings.data.mobile_use.tos_endpoint ?? "",
      tos_region: settings.data.mobile_use.tos_region ?? "",
      use_base64_screenshot: String(settings.data.mobile_use.use_base64_screenshot),
      max_step: String(settings.data.mobile_use.max_step),
      timeout_seconds: String(settings.data.mobile_use.timeout_seconds),
      callback_info: settings.data.mobile_use.callback_info
        ? JSON.stringify(settings.data.mobile_use.callback_info)
        : "",
      output_schema: settings.data.mobile_use.output_schema ?? "",
      retry_limit: String(settings.data.mobile_use.retry_limit),
      system_prompt: settings.data.mobile_use.system_prompt ?? "",
      screen_record: String(settings.data.mobile_use.screen_record),
      mcp_json: settings.data.mobile_use.mcp_json ?? "",
      max_output_tokens: settings.data.mobile_use.max_output_tokens
        ? String(settings.data.mobile_use.max_output_tokens)
        : "",
      gps_info: settings.data.mobile_use.gps_info ?? "",
    });
    setDirtyFields(new Set());
  }, [settings.data]);

  useEffect(() => {
    if (!me.data) return;
    setProfileName(me.data.display_name || me.data.username);
    setProfileEmail(me.data.email || `${me.data.username}@example.com`);
  }, [me.data]);

  useEffect(() => {
    saveThemePreference(theme);
  }, [theme]);

  const saveSettings = useMutation({
    mutationFn: (payload: RunnerSettingsUpdate) =>
      api.put<SettingsResponse>("/settings/runner", payload),
    onSuccess: (response) => {
      queryClient.setQueryData<SettingsResponse>(["settings"], response);
      setValues((current) => ({
        ...current,
        access_key_id: "",
        secret_access_key: "",
      }));
      setDirtyFields(new Set());
      setFieldErrors({});
      setLocalError("");
      setSaved(true);
    },
    onError: (error) => {
      setSaved(false);
      if (!(error instanceof ApiError)) return;
      const field = error.details.field;
      if (typeof field === "string" && field in FIELD_LABELS) {
        const mobileField = field as MobileField;
        setFieldErrors((current) => ({
          ...current,
          [mobileField]: `${FIELD_LABELS[mobileField]} 配置无效`,
        }));
      }
      const missing = error.details.missing_fields;
      if (Array.isArray(missing)) {
        setFieldErrors(
          Object.fromEntries(
            missing
              .filter((field): field is MobileField => typeof field === "string" && field in FIELD_LABELS)
              .map((field) => [field, `${FIELD_LABELS[field]} 为必填项`]),
          ),
        );
      }
    },
  });

  const changePassword = useMutation({
    mutationFn: () =>
      api.post<void>("/auth/password", {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      }),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordMessage("密码已更新，请重新登录。");
    },
    onError: () => {
      setPasswordMessage("");
    },
  });

  const saveError = saveSettings.error instanceof ApiError ? saveSettings.error : null;
  const passwordError =
    changePassword.error instanceof ApiError ? changePassword.error : null;
  const operationPending = saveSettings.isPending || changePassword.isPending;

  function updateValue(field: MobileField, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setDirtyFields((current) => new Set(current).add(field));
    setFieldErrors((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
    setSaved(false);
  }

  function isConfigured(field: MobileField): boolean {
    if (!settings.data) return false;
    if (field === "access_key_id") return settings.data.mobile_use.access_key_id.configured;
    if (field === "secret_access_key") return settings.data.mobile_use.secret_access_key.configured;
    return values[field].trim().length > 0;
  }

  function validate(): boolean {
    const errors = Object.fromEntries(
      REQUIRED_FIELDS
        .filter((field) => values[field].trim().length === 0 && !isConfigured(field))
        .map((field) => [field, `${FIELD_LABELS[field]} 为必填项`]),
    ) as FieldErrors;
    setFieldErrors(errors);
    setLocalError(Object.keys(errors).length > 0 ? "请补齐测试默认配置。" : "");
    return Object.keys(errors).length === 0;
  }

  function saveAll() {
    setSaved(false);
    if (!validate()) return;
    const changedValues: NonNullable<RunnerSettingsUpdate["mobile_use"]> = {};
    for (const field of dirtyFields) {
      const parsed = parseSettingValue(field, values[field]);
      if (parsed === undefined) continue;
      if (
        parsed === false
        && (field === "callback_info" || field === "output_schema" || field === "mcp_json")
      ) return;
      changedValues[field] = parsed as never;
    }
    const payload: RunnerSettingsUpdate = { mode: "mobile_use" };
    if (Object.keys(changedValues).length > 0) {
      payload.mobile_use = changedValues;
    }
    saveSettings.mutate(payload);
  }

  function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordMessage("");
    changePassword.mutate();
  }

  function renderInput(field: MobileField, secret = false) {
    const errorId = `${field}-error`;
    const hintId = `${field}-hint`;
    const configured =
      field === "access_key_id"
        ? settings.data?.mobile_use.access_key_id.configured
        : field === "secret_access_key"
          ? settings.data?.mobile_use.secret_access_key.configured
          : false;
    const accessKeyHint = settings.data?.mobile_use.access_key_id.hint;

    return (
      <div className="settings-field">
        <label htmlFor={`field-${field}`}>{FIELD_LABELS[field]}</label>
        <input
          id={`field-${field}`}
          aria-label={FIELD_LABELS[field]}
          aria-describedby={
            fieldErrors[field] ? errorId : secret && configured ? hintId : undefined
          }
          aria-invalid={Boolean(fieldErrors[field])}
          autoComplete={secret ? "new-password" : "off"}
          type={secret ? "password" : "text"}
          value={values[field]}
          onChange={(event) => updateValue(field, event.target.value)}
        />
        {secret && configured && (
          <p className="field-hint" id={hintId}>
            {field === "access_key_id" && accessKeyHint
              ? `已配置：${accessKeyHint}`
              : "已配置，留空则保留"}
          </p>
        )}
        {fieldErrors[field] && (
          <p className="field-error" id={errorId}>
            {fieldErrors[field]}
          </p>
        )}
      </div>
    );
  }

  function parseSettingValue(field: MobileField, value: string) {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    if (field === "use_base64_screenshot" || field === "screen_record") {
      return trimmed === "true";
    }
    if (
      field === "max_step"
      || field === "timeout_seconds"
      || field === "retry_limit"
      || field === "max_output_tokens"
      || field === "stream_token_ttl_seconds"
    ) {
      return Number(trimmed);
    }
    if (field === "callback_info") {
      try {
        const parsed = JSON.parse(trimmed);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
          setLocalError("CallbackInfo 必须是 JSON 对象。");
          return false;
        }
        return parsed;
      } catch {
        setLocalError("CallbackInfo 不是合法 JSON。");
        return false;
      }
    }
    if (field === "output_schema" || field === "mcp_json") {
      try {
        JSON.parse(trimmed);
      } catch {
        setLocalError(`${FIELD_LABELS[field]} 不是合法 JSON 字符串。`);
        return false;
      }
    }
    return trimmed;
  }

  if (me.isPending || (isAdmin && settings.isPending)) {
    return <p className="panel">正在加载设置...</p>;
  }
  if (isAdmin && settings.isError) {
    return <p className="panel form-error">设置加载失败，请稍后重试。</p>;
  }

  return (
    <div className="settings-page">
      <PageHeader
        className="settings-topbar"
        breadcrumbs={[{ label: "首页", to: "/tasks" }, { label: "设置" }]}
        title="设置"
        description="管理个人偏好、通知策略和 Mobile Use 测试默认配置。"
        actions={
          isAdmin ? (
            <button
              className="primary-button"
              disabled={operationPending}
              type="button"
              onClick={saveAll}
            >
              {saveSettings.isPending ? "保存中..." : "保存所有更改"}
            </button>
          ) : null
        }
      />

      <div className="settings-layout">
        <aside className="settings-nav" aria-label="设置导航">
          <a href="#profile" className="active">
            <UserIcon />
            个人资料
          </a>
          <a href="#password">
            <LockIcon />
            修改密码
          </a>
          {isAdmin && (
            <>
              <div className="nav-divider" />
              <a href="#defaults">
                <SlidersIcon />
                测试默认配置
              </a>
            </>
          )}
        </aside>

        <div className="settings-card">
          <section className="settings-section" id="profile">
            <div className="section-header">
              <div className="profile-header">
                <div className="profile-avatar" aria-hidden="true">
                  {initials(profileName)}
                </div>
                <div>
                  <h2>个人资料</h2>
                  <p className="section-desc">只保留测试平台需要的基础身份信息。</p>
                </div>
              </div>
            </div>
            <div className="settings-grid">
              <div className="settings-field">
                <label htmlFor="profile-name">姓名</label>
                <input
                  id="profile-name"
                  aria-label="姓名"
                  value={profileName}
                  onChange={(event) => setProfileName(event.target.value)}
                />
              </div>
              <div className="settings-field">
                <label htmlFor="profile-email">邮箱</label>
                <input
                  id="profile-email"
                  aria-label="邮箱"
                  type="email"
                  value={profileEmail}
                  onChange={(event) => setProfileEmail(event.target.value)}
                />
              </div>
            </div>

            <div>
              <label style={{ marginBottom: "0.75rem" }}>主题偏好</label>
              <div className="theme-picker" role="radiogroup" aria-label="主题偏好">
                {([
                  ["light", "浅色", <SunIcon key="sun" />],
                  ["dark", "深色", <MoonIcon key="moon" />],
                  ["system", "跟随系统", <MonitorIcon key="monitor" />],
                ] as const).map(([value, label, icon]) => (
                  <label className="theme-option" key={value}>
                    <input
                      checked={theme === value}
                      name="theme"
                      type="radio"
                      value={value}
                      onChange={() => setTheme(value)}
                    />
                    <span className="theme-card">
                      {icon}
                      <span>{label}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </section>

          <section className="settings-section" id="password">
            <div className="section-header">
              <h2>修改密码</h2>
              <p className="section-desc">定期更换密码可以降低长期会话风险。</p>
            </div>
            <form className="password-form" onSubmit={submitPassword}>
              <div className="settings-field">
                <label htmlFor="current-password">当前密码</label>
                <input
                  id="current-password"
                  aria-label="当前密码"
                  autoComplete="current-password"
                  type="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                />
              </div>
              <div className="settings-field">
                <label htmlFor="new-password">新密码</label>
                <input
                  id="new-password"
                  aria-label="新密码"
                  autoComplete="new-password"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                />
              </div>
              <div className="settings-field">
                <label htmlFor="confirm-password">确认新密码</label>
                <input
                  id="confirm-password"
                  aria-label="确认新密码"
                  autoComplete="new-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                />
              </div>
              <button
                className="secondary-button password-submit"
                disabled={changePassword.isPending}
                type="submit"
              >
                {changePassword.isPending ? "更新中..." : "更新密码"}
              </button>
            </form>
            {passwordMessage && <p className="success-message">{passwordMessage}</p>}
            {passwordError && (
              <div className="form-feedback error" role="alert">
                <p>{passwordError.message}</p>
                <RequestId value={passwordError.requestId} />
              </div>
            )}
          </section>

          {isAdmin && (
            <section className="settings-section" id="defaults">
              <div className="section-heading">
                <div className="section-header">
                  <h2>测试默认配置</h2>
                  <p className="section-desc">
                    默认使用 Mobile Use。密钥只支持覆盖更新，不会回填原值。
                  </p>
                </div>
                <Link className="secondary-button" to="/pods">
                  刷新与查看 Pod 池
                </Link>
              </div>
              <div className="settings-grid">
                {renderInput("access_key_id", true)}
                {renderInput("secret_access_key", true)}
                {renderInput("product_id")}
                {renderInput("account_id")}
                {renderInput("sts_role_trn")}
                {renderInput("stream_token_ttl_seconds")}
                {renderInput("tos_bucket")}
                {renderInput("tos_endpoint")}
                {renderInput("tos_region")}
                {renderInput("use_base64_screenshot")}
                {renderInput("max_step")}
                {renderInput("timeout_seconds")}
                {renderInput("retry_limit")}
                {renderInput("screen_record")}
                {renderInput("max_output_tokens")}
                {renderInput("system_prompt")}
                {renderInput("callback_info")}
                {renderInput("output_schema")}
                {renderInput("mcp_json")}
                {renderInput("gps_info")}
              </div>
            </section>
          )}
        </div>
      </div>

      <div aria-live="polite" className="settings-feedback">
        {localError && <p className="form-error">{localError}</p>}
        {saveError && (
          <div className="form-feedback error" role="alert">
            <p>{saveError.message}</p>
            <RequestId value={saveError.requestId} />
          </div>
        )}
        {saved && <p className="success-message">设置已保存。</p>}
      </div>
    </div>
  );
}
