import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './client'

function isClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500
}

/** Shared retry policy: never retry a 4xx (it won't succeed by retrying), exponential backoff
 * capped at 30s for anything else (5xx, network errors). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => !isClientError(error) && failureCount < 3,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      },
      mutations: {
        retry: (failureCount, error) => !isClientError(error) && failureCount < 2,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      },
    },
  })
}
