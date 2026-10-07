import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 45_000 },
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.FORMA_E2E_URL ?? 'http://127.0.0.1:5178',
    viewport: { width: 1440, height: 960 },
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  reporter: [['list']],
});
