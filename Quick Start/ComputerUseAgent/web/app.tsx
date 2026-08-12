import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router";

import { AppShell } from "./components/app-shell";
import { BusinessProvider } from "./business-context";
import { SetupPage } from "./pages/setup-page";
import { LoginPage } from "./pages/login-page";
import { TaskListPage } from "./pages/task-list-page";
import { CreateTaskPage } from "./pages/create-task-page";
import { TaskDetailPage } from "./pages/task-detail-page";
import { TaskOverviewPage } from "./pages/task-overview-page";
import { TaskReportPage } from "./pages/task-report-page";
import { TaskTracePage } from "./pages/task-trace-page";
import { PodPoolPage } from "./pages/pod-pool-page";
import { SettingsPage } from "./pages/settings-page";
import { CasesPage } from "./pages/cases-page";
import { CaseImportPreviewPage } from "./pages/case-import-preview-page";
import { CaseEditorPage } from "./pages/case-editor-page";
import { UsersPage } from "./pages/users-page";
import { api, subscribeUnauthorized } from "./api/client";
import type { SetupStatus, User } from "./api/types";
import { initializeThemePreference } from "./utils/theme";

initializeThemePreference();

const TestPlanDetailPage = lazy(() =>
  import("./pages/test-plan-detail-page").then((module) => ({
    default: module.TestPlanDetailPage,
  })));
const TestPlanRunPage = lazy(() =>
  import("./pages/test-plan-run-page").then((module) => ({
    default: module.TestPlanRunPage,
  })));
const TestPlanListPage = lazy(() =>
  import("./pages/test-plan-list-page").then((module) => ({
    default: module.TestPlanListPage,
  })));
const TestPlanEditorPage = lazy(() =>
  import("./pages/test-plan-editor-page").then((module) => ({
    default: module.TestPlanEditorPage,
  })));
const TaskReportListPage = lazy(() =>
  import("./pages/task-report-list-page").then((module) => ({
    default: module.TaskReportListPage,
  })));
const PlanExecutionReportPage = lazy(() =>
  import("./pages/plan-execution-report-page").then((module) => ({
    default: module.PlanExecutionReportPage,
  })));

function PageLoadingFallback() {
  return <div className="route-loading">加载中...</div>;
}

function AuthGate() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(
    () => subscribeUnauthorized(() => {
      queryClient.setQueryData(["me"], null);
    }),
    [queryClient],
  );

  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => api.get<SetupStatus>("/setup/status"),
    retry: false,
  });

  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<User>("/auth/me"),
    retry: false,
    enabled: setupStatus.data?.initialized === true,
  });

  if (setupStatus.isLoading) {
    return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", color: "#64748b", fontSize: "0.875rem" }}>加载中...</div>;
  }

  if (!setupStatus.data?.initialized) {
    return (
      <SetupPage
        onAlreadyInitialized={() => {
          queryClient.setQueryData(["setup-status"], { initialized: true });
          setupStatus.refetch();
        }}
        onAuthenticated={(user) => {
          queryClient.setQueryData(["me"], user);
          queryClient.setQueryData(["setup-status"], { initialized: true });
          navigate("/tasks", { replace: true });
        }}
      />
    );
  }

  if (me.isLoading) {
    return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", color: "#64748b", fontSize: "0.875rem" }}>加载中...</div>;
  }

  if (!me.data) {
    return (
      <LoginPage
        onAuthenticated={(user) => {
          queryClient.setQueryData(["me"], user);
          navigate("/tasks", { replace: true });
        }}
      />
    );
  }

  return (
    <BusinessProvider>
      <AppShell user={me.data}>
        <Routes>
        <Route index element={<Navigate to="/tasks" replace />} />
        <Route path="tasks">
          <Route index element={<TaskListPage />} />
          <Route path="new" element={<CreateTaskPage />} />
          <Route path=":taskId" element={<TaskDetailPage />}>
            <Route index element={<TaskOverviewPage />} />
            <Route path="report" element={<TaskReportPage />} />
            <Route path="trace" element={<TaskTracePage />} />
          </Route>
        </Route>
        <Route path="cases">
          <Route index element={<CasesPage />} />
          <Route path="new" element={<CaseEditorPage />} />
          <Route path="import/preview" element={<CaseImportPreviewPage />} />
          <Route path=":caseId/edit" element={<CaseEditorPage />} />
        </Route>
        <Route path="test-plans">
          <Route
            index
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <TestPlanListPage />
              </Suspense>
            }
          />
          <Route
            path="new"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <TestPlanEditorPage />
              </Suspense>
            }
          />
          <Route
            path=":planId"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <TestPlanDetailPage />
              </Suspense>
            }
          />
          <Route
            path=":planId/run"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <TestPlanRunPage />
              </Suspense>
            }
          />
          <Route
            path=":planId/edit"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <TestPlanEditorPage />
              </Suspense>
            }
          />
        </Route>
        <Route path="task-reports">
          <Route
            index
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <TaskReportListPage />
              </Suspense>
            }
          />
          <Route
            path=":executionId"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <PlanExecutionReportPage />
              </Suspense>
            }
          />
        </Route>
        <Route path="pods" element={<PodPoolPage />} />
        <Route
          path="users"
          element={me.data.role === "admin" ? <UsersPage /> : <Navigate to="/tasks" replace />}
        />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/tasks" replace />} />
        </Routes>
      </AppShell>
    </BusinessProvider>
  );
}

export function App() {
  return <AuthGate />;
}
