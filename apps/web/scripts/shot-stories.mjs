#!/usr/bin/env node
// make shot-stories -- builds Storybook, serves it, screenshots every story at
// 1280px/390px in both themes into .screenshots/, then tears the server down.
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import { createReadStream, existsSync, statSync, realpathSync } from 'node:fs'
import { createServer } from 'node:http'
import { execSync } from 'node:child_process'
import path from 'node:path'

const STATIC_DIR = path.resolve(process.cwd(), 'storybook-static')
const OUT_DIR = path.resolve(process.cwd(), '.screenshots')
const WIDTHS = [1280, 390]
const THEMES = ['light', 'dark']
const PORT = 6007

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' }

function serveStatic() {
  const root = realpathSync(STATIC_DIR)
  return createServer((req, res) => {
    const reqPath = req.url === '/' ? '/index.html' : req.url.split('?')[0]
    const requested = path.resolve(root, '.' + path.posix.normalize(decodeURIComponent(reqPath)))
    let real
    try {
      real = existsSync(requested) && statSync(requested).isFile() ? realpathSync(requested) : null
    } catch {
      real = null
    }
    if (!real || (real !== root && !real.startsWith(root + path.sep))) {
      res.writeHead(404)
      res.end('not found')
      return
    }
    res.writeHead(200, { 'content-type': MIME[path.extname(real)] ?? 'application/octet-stream' })
    createReadStream(real).pipe(res)
  }).listen(PORT, '127.0.0.1')
}

async function main() {
  console.log('Building Storybook...')
  execSync('npx storybook build --quiet', { stdio: 'inherit' })

  await mkdir(OUT_DIR, { recursive: true })
  const server = serveStatic()
  const base = `http://localhost:${PORT}`

  const index = await fetch(`${base}/index.json`).then((r) => r.json())
  const stories = Object.values(index.entries ?? index.stories ?? {}).filter((s) => s.type === 'story')

  const browser = await chromium.launch()
  const page = await browser.newPage()

  for (const story of stories) {
    const slug = story.id.replace(/[^a-z0-9-]/gi, '_')
    for (const theme of THEMES) {
      await page.goto(`${base}/iframe.html?id=${story.id}&viewMode=story&globals=theme:${theme}`, {
        waitUntil: 'networkidle',
      })
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 900 })
        const file = path.join(OUT_DIR, `${slug}-${width}-${theme}.png`)
        await page.screenshot({ path: file, fullPage: true })
        console.log(`wrote ${file}`)
      }
    }
  }

  await browser.close()
  server.close()
}

main()
