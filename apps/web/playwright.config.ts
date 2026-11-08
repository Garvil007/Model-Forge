import { defineConfig, devices } from '@playwright/test'

// Set by the nightly dev-smoke workflow (.github/workflows/e2e-nightly.yml) to point the
// existing suite at a real deployment instead of the local preview build. Unset in the
// regular PR workflow, which keeps using the local webServer below.
const remoteBaseURL = process.env.PLAYWRIGHT_BASE_URL

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: remoteBaseURL ?? 'http://localhost:4173',
    trace: 'on-first-retry',
  },
  // Only start/build the local preview server when no remote baseURL is given — a nightly
  // run against a dev deployment has nothing to build or serve locally.
  webServer: remoteBaseURL
    ? undefined
    : {
        command: 'npm run build && npm run preview -- --port 4173',
        url: 'http://localhost:4173',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
