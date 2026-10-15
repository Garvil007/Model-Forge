import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

// Dev-only escape hatch: routes under these path prefixes fall through to the real
// network (and vite's dev proxy) instead of being mocked, so apps/api can be exercised
// against LocalStack without losing MSW for everything else or for tests (server.ts
// imports the full `handlers` list directly and is unaffected).
const livePrefixes = (import.meta.env.VITE_LIVE_API_PATHS ?? '')
  .split(',')
  .map((p: string) => p.trim())
  .filter(Boolean)

const activeHandlers = livePrefixes.length
  ? handlers.filter((handler) => {
      const path = String(handler.info.path)
      return !livePrefixes.some((prefix) => path.startsWith(prefix))
    })
  : handlers

export const worker = setupWorker(...activeHandlers)
