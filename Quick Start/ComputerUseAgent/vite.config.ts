import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

const backendTarget = "http://localhost:8001";

export default defineConfig({
  plugins: [react()],
  root: ".",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": backendTarget,
      "/health": backendTarget,
      "/novnc": {
        target: backendTarget,
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    exclude: [...configDefaults.exclude, "tests/e2e/**"],
    setupFiles: ["./tests/frontend/setup.ts"],
  },
});
