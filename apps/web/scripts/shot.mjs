#!/usr/bin/env node
// make shot PAGE=<url> -- screenshots PAGE at 1280px and 390px, in both themes.
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const args = process.argv.slice(2)
const pageIndex = args.indexOf('--page')
const page = pageIndex === -1 ? process.env.PAGE : args[pageIndex + 1]
const name = args.includes('--name') ? args[args.indexOf('--name') + 1] : 'page'

if (!page) {
  console.error('Usage: node scripts/shot.mjs --page <url> [--name <name>]')
  process.exit(1)
}

const OUT_DIR = path.resolve(process.cwd(), '.screenshots')
const WIDTHS = [1280, 390]
const THEMES = ['light', 'dark']

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const browser = await chromium.launch()
  const browserPage = await browser.newPage()
  await browserPage.goto(page, { waitUntil: 'networkidle' })

  for (const theme of THEMES) {
    await browserPage.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme)
    for (const width of WIDTHS) {
      await browserPage.setViewportSize({ width, height: 900 })
      const file = path.join(OUT_DIR, `${name}-${width}-${theme}.png`)
      await browserPage.screenshot({ path: file, fullPage: true })
      console.log(`wrote ${file}`)
    }
  }

  await browser.close()
}

main()
