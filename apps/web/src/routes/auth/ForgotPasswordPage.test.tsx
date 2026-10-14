import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { authProvider } from '../../auth/provider'
import { AuthProvider } from '../../auth/AuthProvider'
import { ToastProvider } from '../../ui/toast/ToastProvider'
import { ForgotPasswordPage } from './ForgotPasswordPage'

function renderPage() {
  render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/forgot-password']}>
        <AuthProvider>
          <Routes>
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/login" element={<p>Login page</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('ForgotPasswordPage', () => {
  beforeEach(async () => {
    localStorage.clear()
    await authProvider.signUp('reset@user.com', 'OldPassword1!')
    await authProvider.confirmSignUp('reset@user.com', '123456')
    await authProvider.signOut()
  })
  afterEach(() => localStorage.clear())

  it('moves to the reset stage after requesting a code', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'reset@user.com')
    await user.click(screen.getByRole('button', { name: 'Send code' }))
    expect(await screen.findByRole('heading', { name: 'Reset your password' })).toBeInTheDocument()
  })

  it('resets the password and redirects to /login', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'reset@user.com')
    await user.click(screen.getByRole('button', { name: 'Send code' }))
    await screen.findByRole('heading', { name: 'Reset your password' })

    await user.type(screen.getByLabelText('Verification code'), '123456')
    await user.type(screen.getByLabelText(/^New password/), 'NewPassword1!')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))
    await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument())
  })
})
