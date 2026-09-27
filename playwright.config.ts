import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

const testDir = defineBddConfig({
  features: "features/**/*.feature",
  steps: "features/steps/**/*.ts",
});

export default defineConfig({
  testDir,
  timeout: 30_000,
  workers: 1,
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:3000" },
  webServer: {
    command: "uv run python scripts/e2e_stack.py",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
