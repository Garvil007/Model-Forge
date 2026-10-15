import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useToast } from '../ui/toast/useToast'
import { AuthContext, type AuthContextValue } from './AuthContext'
import { attachTokenSync, authProvider } from './provider'
import type { AuthUser } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const { showToast } = useToast()

  useEffect(() => {
    authProvider.getCurrentUser().then((current) => {
      setUser(current)
      setIsLoading(false)
    })
  }, [])

  const signUp = useCallback(async (email: string, password: string) => {
    await authProvider.signUp(email, password)
  }, [])

  const confirmSignUp = useCallback(async (email: string, code: string) => {
    const confirmed = await authProvider.confirmSignUp(email, code)
    setUser(confirmed)
  }, [])

  const resendConfirmationCode = useCallback(async (email: string) => {
    await authProvider.resendConfirmationCode(email)
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const signedIn = await authProvider.signIn(email, password)
    setUser(signedIn)
  }, [])

  const signInWithGoogle = useCallback(async () => {
    const signedIn = await authProvider.signInWithGoogle()
    setUser(signedIn)
  }, [])

  const signOut = useCallback(async () => {
    await authProvider.signOut()
    setUser(null)
  }, [])

  const forgotPassword = useCallback(async (email: string) => {
    await authProvider.forgotPassword(email)
  }, [])

  const confirmForgotPassword = useCallback(
    async (email: string, code: string, newPassword: string) => {
      await authProvider.confirmForgotPassword(email, code, newPassword)
    },
    [],
  )

  const expireSession = useCallback(() => {
    setUser(null)
    showToast({ message: 'Your session expired. Please log in again.', variant: 'warning' })
  }, [showToast])

  useEffect(() => attachTokenSync(expireSession), [expireSession])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      signUp,
      confirmSignUp,
      resendConfirmationCode,
      signIn,
      signInWithGoogle,
      signOut,
      forgotPassword,
      confirmForgotPassword,
      expireSession,
    }),
    [
      user,
      isLoading,
      signUp,
      confirmSignUp,
      resendConfirmationCode,
      signIn,
      signInWithGoogle,
      signOut,
      forgotPassword,
      confirmForgotPassword,
      expireSession,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
