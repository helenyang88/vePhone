import { defineConfig, devices } from "@playwright/test";

const e2ePort = (
  globalThis as {
    process?: { env?: Record<string, string | undefined> };
  }
).process?.env?.E2E_PORT ?? "8000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${e2ePort}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `make e2e-server E2E_PORT=${e2ePort}`,
    url: `http://127.0.0.1:${e2ePort}/health/ready`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
