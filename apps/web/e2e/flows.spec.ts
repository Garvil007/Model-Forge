import { expect, test } from '@playwright/test'
import { logIn, seedConfirmedUser } from './helpers'

test.describe('core user journeys', () => {
  test('sign up, verify, log in, log out', async ({ page }) => {
    const email = `signup-${Date.now()}@modelforge.dev`
    await page.goto('/signup')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel(/^Password/).fill('Password1!')
    await page.getByLabel('Confirm password').fill('Password1!')
    await page.getByRole('button', { name: 'Create account' }).click()

    await expect(page.getByRole('heading', { name: 'Verify your email' })).toBeVisible()
    await page.getByLabel('Verification code').fill('123456')
    await page.getByRole('button', { name: 'Verify' }).click()
    await page.waitForURL('**/app')
    await expect(page.getByRole('heading', { name: 'ModelForge' })).toBeVisible()

    await page.getByRole('button', { name: email }).click()
    await page.getByRole('menuitem', { name: 'Log out' }).click()
    await page.waitForURL('**/')
    await expect(page.getByRole('link', { name: 'Log in' })).toBeVisible()

    await logIn(page, email, 'Password1!')
    await page.waitForURL('**/app')
    await expect(page.getByRole('heading', { name: 'ModelForge' })).toBeVisible()
  })

  test('upload a model, pick a method, run it, see the result, and download', async ({
    page,
  }) => {
    await seedConfirmedUser(page, `upload-${Date.now()}@modelforge.dev`)

    await page.locator('input[type="file"]').setInputFiles({
      name: 'resnet50.onnx',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('fake-onnx-model-bytes'),
    })

    await expect(page.getByText('resnet50.onnx')).toBeVisible({ timeout: 10_000 })

    await page.getByRole('radio', { name: 'INT8 dynamic' }).check()
    await page.getByRole('button', { name: /Compress with/i }).click()

    const downloadButton = page.getByRole('button', { name: /^Download/ })
    await expect(downloadButton).toBeVisible({ timeout: 20_000 })
    await downloadButton.click()
    await expect(
      page.getByText('Downloads are available once the backend is connected.'),
    ).toBeVisible()
  })

  test('starts a job and cancels it', async ({ page }) => {
    await seedConfirmedUser(page, `cancel-${Date.now()}@modelforge.dev`)

    await page.locator('input[type="file"]').setInputFiles({
      name: 'resnet50.onnx',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('fake-onnx-model-bytes'),
    })
    await expect(page.getByText('resnet50.onnx')).toBeVisible({ timeout: 10_000 })

    await page.getByRole('radio', { name: 'INT8 dynamic' }).check()
    await page.getByRole('button', { name: /Compress with/i }).click()
    await page.getByRole('button', { name: 'Cancel job' }).click()
    await page
      .getByRole('alertdialog')
      .getByRole('button', { name: 'Cancel job' })
      .click()

    await expect(page.getByText('Job canceled.')).toBeVisible({ timeout: 10_000 })
  })
})
