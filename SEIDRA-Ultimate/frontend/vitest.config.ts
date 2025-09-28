import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    exclude: ["tests/e2e/**", "e2e/**", "node_modules/**"],
    coverage: {
      reporter: ["text", "json", "html"],
      reportsDirectory: "../reports/qa/frontend",
    },
  },
});
