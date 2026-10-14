import { createMockAuthProvider } from './mockAuthProvider'
import type { AuthProvider } from './types'

export type { AuthProvider, AuthUser } from './types'
export { AuthApiError } from './types'

export const authProvider: AuthProvider = createMockAuthProvider()
