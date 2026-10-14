// One-off: screenshot routes that require a signed-in session, by seeding the mock auth
// provider's localStorage keys directly (same shape as src/auth/mockAuthProvider.ts).
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const OUT_DIR = path.resolve(process.cwd(), '.screenshots')
const BASE = 'http://localhost:4173'
const ROUTES = [
  { path: '/app', name: 'tool' },
  { path: '/dashboard', name: 'dashboard' },
  { path: '/settings', name: 'settings' },
]

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  await page.goto(BASE)
  await page.evaluate(() => {
    const user = { id: 'shot-user', email: 'shot@modelforge.dev', password: 'Password1!', confirmed: true }
    localStorage.setItem('modelforge.auth.users', JSON.stringify([user]))
    localStorage.setItem('modelforge.auth.session', user.id)
  })

  for (const route of ROUTES) {
    await page.goto(`${BASE}${route.path}`, { waitUntil: 'networkidle' })
    for (const theme of ['light', 'dark']) {
      await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme)
      for (const width of [1280, 390]) {
        await page.setViewportSize({ width, height: 900 })
        const file = path.join(OUT_DIR, `${route.name}-${width}-${theme}.png`)
        await page.screenshot({ path: file, fullPage: true })
        console.log(`wrote ${file}`)
      }
    }
  }

  await browser.close()
}

main()
