import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { seedConfirmedUser } from './helpers'

const PUBLIC_ROUTES = ['/', '/login', '/signup', '/forgot-password', '/pricing', '/not-a-route']

test.describe('accessibility', () => {
  for (const route of PUBLIC_ROUTES) {
    for (const theme of ['light', 'dark'] as const) {
      test(`${route} has no axe violations (${theme})`, async ({ page }) => {
        await page.goto(route)
        await page.getByRole('banner').waitFor()
        await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme)
        const results = await new AxeBuilder({ page }).analyze()
        expect(results.violations).toEqual([])
      })
    }
  }

  test('/app, /dashboard, and /settings have no axe violations once signed in', async ({
    page,
  }) => {
    await seedConfirmedUser(page)
    for (const route of ['/app', '/dashboard', '/settings']) {
      await page.goto(route)
      await page.getByRole('banner').waitFor()
      const results = await new AxeBuilder({ page }).analyze()
      expect(results.violations).toEqual([])
    }
  })
})
