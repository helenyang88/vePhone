import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

const viteConfig = readFileSync("vite.config.ts", "utf8");
const envExample = readFileSync(".env.example", "utf8");

it("uses isolated local ports for the CUA frontend and backend proxy", () => {
  expect(viteConfig).toContain('const backendTarget = "http://localhost:8001";');
  expect(viteConfig).toContain("port: 5174");
  expect(viteConfig).toContain("strictPort: true");
  expect(viteConfig).toContain('"/api": backendTarget');
  expect(viteConfig).toContain('"/health": backendTarget');
  expect(viteConfig).toContain("target: backendTarget");
  expect(envExample).toContain("APP_BASE_URL=http://localhost:8001");
});
