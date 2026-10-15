import type { ApiErrorBody } from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

let authToken: string | null = null
export function setAuthToken(token: string | null): void {
  authToken = token
}

function authHeaders(): Record<string, string> {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {}
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody
    return new ApiError(response.status, body.error.code, body.error.message)
  } catch {
    return new ApiError(response.status, 'unknown_error', response.statusText)
  }
}

export interface RequestOptions {
  signal?: AbortSignal
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...init.headers },
  })
  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const apiClient = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { method: 'GET', signal: options?.signal })
  },
  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: options?.signal,
    })
  },
  /** Raw (non-JSON) request for S3-style part uploads — returns the `Response` so callers can
   * read headers like `ETag`, and never tries to parse a body. */
  async putRaw(path: string, body: Blob, options?: RequestOptions): Promise<Response> {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: 'PUT',
      body,
      signal: options?.signal,
    })
    if (!response.ok) throw await toApiError(response)
    return response
  },
  /** PUTs a part directly to a presigned S3 URL — no base URL, no auth header (the
   * signature in the URL is the auth), and the body never touches our API at all. */
  async putPresigned(url: string, body: Blob, options?: RequestOptions): Promise<Response> {
    const response = await fetch(url, { method: 'PUT', body, signal: options?.signal })
    if (!response.ok) {
      throw new ApiError(
        response.status,
        'upload_failed',
        `Part upload failed (${response.status}).`,
      )
    }
    return response
  },
}
