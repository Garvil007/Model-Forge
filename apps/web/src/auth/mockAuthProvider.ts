import type { AuthProvider, AuthUser } from './types'
import { AuthApiError } from './types'

interface StoredUser {
  id: string
  email: string
  password: string
  confirmed: boolean
}

const USERS_KEY = 'modelforge.auth.users'
const SESSION_KEY = 'modelforge.auth.session'
const PENDING_CODE = '123456'
const LATENCY_MS = 400

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS))
}

function readUsers(): StoredUser[] {
  try {
    const raw = localStorage.getItem(USERS_KEY)
    return raw ? (JSON.parse(raw) as StoredUser[]) : []
  } catch {
    return []
  }
}

function writeUsers(users: StoredUser[]): void {
  try {
    localStorage.setItem(USERS_KEY, JSON.stringify(users))
  } catch {
    // storage unavailable (private mode, quota) — mock session is best-effort only
  }
}

function setSession(userId: string | null): void {
  try {
    if (userId) localStorage.setItem(SESSION_KEY, userId)
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    // ignore
  }
}

function toAuthUser(user: StoredUser): AuthUser {
  return { id: user.id, email: user.email }
}

export function createMockAuthProvider(): AuthProvider {
  return {
    async getCurrentUser() {
      let sessionUserId: string | null = null
      try {
        sessionUserId = localStorage.getItem(SESSION_KEY)
      } catch {
        return null
      }
      if (!sessionUserId) return null
      const user = readUsers().find((candidate) => candidate.id === sessionUserId)
      return user ? toAuthUser(user) : null
    },

    async signUp(email, password) {
      await delay(undefined)
      const users = readUsers()
      if (users.some((candidate) => candidate.email === email)) {
        throw new AuthApiError('UserAlreadyExists', 'An account with this email already exists.')
      }
      users.push({ id: crypto.randomUUID(), email, password, confirmed: false })
      writeUsers(users)
    },

    async confirmSignUp(email, code) {
      await delay(undefined)
      if (code !== PENDING_CODE) {
        throw new AuthApiError(
          'CodeMismatch',
          'That code is incorrect. Check your email and try again.',
        )
      }
      const users = readUsers()
      const user = users.find((candidate) => candidate.email === email)
      if (!user) {
        throw new AuthApiError('UserNotFound', 'We could not find that account.')
      }
      user.confirmed = true
      writeUsers(users)
      setSession(user.id)
      return toAuthUser(user)
    },

    async resendConfirmationCode() {
      await delay(undefined)
    },

    async signIn(email, password) {
      await delay(undefined)
      const user = readUsers().find((candidate) => candidate.email === email)
      if (!user || user.password !== password) {
        throw new AuthApiError('NotAuthorized', 'Incorrect email or password.')
      }
      if (!user.confirmed) {
        throw new AuthApiError('UserNotConfirmed', 'Verify your email before signing in.')
      }
      setSession(user.id)
      return toAuthUser(user)
    },

    async signInWithGoogle() {
      await delay(undefined)
      const email = 'google-user@example.com'
      const users = readUsers()
      let user = users.find((candidate) => candidate.email === email)
      if (!user) {
        user = { id: crypto.randomUUID(), email, password: '', confirmed: true }
        users.push(user)
        writeUsers(users)
      }
      setSession(user.id)
      return toAuthUser(user)
    },

    async signOut() {
      await delay(undefined)
      setSession(null)
    },

    async forgotPassword() {
      await delay(undefined)
    },

    async confirmForgotPassword(email, code, newPassword) {
      await delay(undefined)
      if (code !== PENDING_CODE) {
        throw new AuthApiError(
          'CodeMismatch',
          'That code is incorrect. Check your email and try again.',
        )
      }
      const users = readUsers()
      const user = users.find((candidate) => candidate.email === email)
      if (!user) {
        throw new AuthApiError('UserNotFound', 'We could not find that account.')
      }
      user.password = newPassword
      writeUsers(users)
    },
  }
}
