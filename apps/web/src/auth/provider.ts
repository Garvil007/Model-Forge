import { attachCognitoTokenSync, createCognitoAuthProvider } from './cognitoAuthProvider'
import { createMockAuthProvider } from './mockAuthProvider'
import type { AuthProvider } from './types'

export type { AuthProvider, AuthUser } from './types'
export { AuthApiError } from './types'

const isCognito = import.meta.env.VITE_AUTH_PROVIDER === 'cognito'

export const authProvider: AuthProvider = isCognito
  ? createCognitoAuthProvider()
  : createMockAuthProvider()

/** No-op for the mock provider; for Cognito, keeps the API client's bearer token in sync with
 * the Amplify session and reports a failed silent refresh via `onSessionExpired`. */
export const attachTokenSync: (onSessionExpired: () => void) => () => void = isCognito
  ? attachCognitoTokenSync
  : () => () => {}
