import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { resetDb } from '../mocks/db'
import { server } from '../mocks/server'

// Lazy-loaded routes (React.lazy) can take longer than the default 1s under full-suite CPU load.
configure({ asyncUtilTimeout: 10_000 })

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  server.resetHandlers()
  resetDb()
})
afterAll(() => server.close())
