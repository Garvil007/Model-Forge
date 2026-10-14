import type { Page } from '@playwright/test'

export const TEST_EMAIL = 'e2e@modelforge.dev'
export const TEST_PASSWORD = 'Password1!'

/** Signs up, verifies (the mock provider's fixed code), and logs out — a known account
 * for tests that need an existing user without driving the UI every time. */
export async function seedConfirmedUser(page: Page, email = TEST_EMAIL, password = TEST_PASSWORD) {
  await page.goto('/signup')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await page.getByRole('button', { name: 'Create account' }).click()
  await page.getByLabel('Verification code').fill('123456')
  await page.getByRole('button', { name: 'Verify' }).click()
  await page.waitForURL('**/app')
}

export async function logIn(page: Page, email = TEST_EMAIL, password = TEST_PASSWORD) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Log in' }).click()
}
