import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import catalogJson from '../features/catalog/generated/catalog.json'
import type { Catalog } from '../features/catalog/generated/catalog.types'
import { setCatalog } from '../features/catalog/types'
import { resetDb } from '../mocks/db'
import { server } from '../mocks/server'

// Lazy-loaded routes (React.lazy) can take longer than the default 1s under full-suite CPU load.
configure({ asyncUtilTimeout: 10_000 })

// main.tsx normally fetches /catalog before render; tests never run main.tsx, so seed the same
// fixture directly to keep CATALOG populated exactly as it was before it became fetch-driven.
beforeAll(() => setCatalog(catalogJson as Catalog))
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  server.resetHandlers()
  resetDb()
})
afterAll(() => server.close())
