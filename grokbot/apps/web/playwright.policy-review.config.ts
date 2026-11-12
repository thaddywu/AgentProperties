import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e-policy-review",
  workers: 1,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  outputDir: "./test-results/policy-review",
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:5188",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "pnpm exec vite --config vite.nova.config.ts --port 5188",
    url: "http://127.0.0.1:5188/policy-review.html",
    reuseExistingServer: !process.env.CI,
    env: { MODEL_CONNECTION_FILE: "" },
  },
});
