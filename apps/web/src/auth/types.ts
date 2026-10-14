export interface AuthUser {
  id: string
  email: string
}

export class AuthApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

export interface AuthProvider {
  getCurrentUser(): Promise<AuthUser | null>
  signUp(email: string, password: string): Promise<void>
  confirmSignUp(email: string, code: string): Promise<AuthUser>
  resendConfirmationCode(email: string): Promise<void>
  signIn(email: string, password: string): Promise<AuthUser>
  signInWithGoogle(): Promise<AuthUser>
  signOut(): Promise<void>
  forgotPassword(email: string): Promise<void>
  confirmForgotPassword(email: string, code: string, newPassword: string): Promise<void>
}
