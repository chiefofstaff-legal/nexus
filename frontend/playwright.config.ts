import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3100",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "npm run dev",
      url: "http://localhost:3100",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "python -m uvicorn app.main:app --port 8100",
      cwd: "../backend",
      url: "http://localhost:8100/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
