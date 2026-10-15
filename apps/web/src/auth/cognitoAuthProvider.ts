import {
  autoSignIn,
  confirmResetPassword,
  confirmSignUp as amplifyConfirmSignUp,
  fetchAuthSession,
  fetchUserAttributes,
  getCurrentUser as amplifyGetCurrentUser,
  resendSignUpCode,
  resetPassword,
  signIn as amplifySignIn,
  signInWithRedirect,
  signOut as amplifySignOut,
  signUp as amplifySignUp,
} from 'aws-amplify/auth'
import { Hub } from 'aws-amplify/utils'
import { setAuthToken } from '../api/client'
import { configureAmplify } from './amplifyConfig'
import type { AuthProvider, AuthUser } from './types'
import { AuthApiError } from './types'

function toAuthApiError(error: unknown): AuthApiError {
  if (error instanceof Error) {
    return new AuthApiError(error.name || 'UnknownError', error.message)
  }
  return new AuthApiError('UnknownError', 'Something went wrong. Please try again.')
}

async function buildAuthUser(): Promise<AuthUser> {
  const current = await amplifyGetCurrentUser()
  const attributes = await fetchUserAttributes()
  return { id: current.userId, email: attributes.email ?? '' }
}

export function createCognitoAuthProvider(): AuthProvider {
  configureAmplify()

  return {
    async getCurrentUser() {
      try {
        return await buildAuthUser()
      } catch {
        return null
      }
    },

    async signUp(email, password) {
      try {
        await amplifySignUp({
          username: email,
          password,
          options: { userAttributes: { email }, autoSignIn: true },
        })
      } catch (error) {
        throw toAuthApiError(error)
      }
    },

    async confirmSignUp(email, code) {
      try {
        await amplifyConfirmSignUp({ username: email, confirmationCode: code })
        await autoSignIn()
        return await buildAuthUser()
      } catch (error) {
        throw toAuthApiError(error)
      }
    },

    async resendConfirmationCode(email) {
      try {
        await resendSignUpCode({ username: email })
      } catch (error) {
        throw toAuthApiError(error)
      }
    },

    async signIn(email, password) {
      try {
        const result = await amplifySignIn({ username: email, password })
        if (result.nextStep.signInStep === 'CONFIRM_SIGN_UP') {
          throw new AuthApiError('UserNotConfirmed', 'Verify your email before signing in.')
        }
        return await buildAuthUser()
      } catch (error) {
        throw error instanceof AuthApiError ? error : toAuthApiError(error)
      }
    },

    async signInWithGoogle() {
      // The browser navigates away to the Cognito hosted UI and back; this promise never
      // resolves in-page. On return, the Hub 'signedIn' event (see attachTokenSync below)
      // is what updates AuthProvider's user state, not this call's resolution.
      await signInWithRedirect({ provider: 'Google' })
      return new Promise<AuthUser>(() => {})
    },

    async signOut() {
      await amplifySignOut()
    },

    async forgotPassword(email) {
      try {
        await resetPassword({ username: email })
      } catch (error) {
        throw toAuthApiError(error)
      }
    },

    async confirmForgotPassword(email, code, newPassword) {
      try {
        await confirmResetPassword({ username: email, confirmationCode: code, newPassword })
      } catch (error) {
        throw toAuthApiError(error)
      }
    },
  }
}

async function syncAuthToken(): Promise<void> {
  try {
    const session = await fetchAuthSession()
    setAuthToken(session.tokens?.accessToken?.toString() ?? null)
  } catch {
    setAuthToken(null)
  }
}

/** Keeps `apiClient`'s bearer token in sync with Amplify's session, and routes a failed
 * silent refresh to the session-expired toast instead of leaving the UI on stale auth. */
export function attachCognitoTokenSync(onSessionExpired: () => void): () => void {
  void syncAuthToken()
  return Hub.listen('auth', ({ payload }) => {
    switch (payload.event) {
      case 'signedIn':
      case 'tokenRefresh':
        void syncAuthToken()
        break
      case 'signedOut':
        setAuthToken(null)
        break
      case 'tokenRefresh_failure':
        setAuthToken(null)
        onSessionExpired()
        break
    }
  })
}
