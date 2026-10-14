import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { authProvider } from '../../auth/provider'
import { AuthProvider } from '../../auth/AuthProvider'
import { ToastProvider } from '../../ui/toast/ToastProvider'
import { LoginPage } from './LoginPage'

function renderPage() {
  render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/app" element={<p>Tool page</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('shows an inline error for an invalid email', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.type(screen.getByLabelText('Password'), 'whatever')
    await user.click(screen.getByRole('button', { name: 'Log in' }))
    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
  })

  it('shows a form error for wrong credentials', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'a@b.com')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByText('Incorrect email or password.')).toBeInTheDocument()
  })

  it('logs in and navigates to /app on success', async () => {
    await authProvider.signUp('a@b.com', 'Password1!')
    await authProvider.confirmSignUp('a@b.com', '123456')
    await authProvider.signOut()

    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'a@b.com')
    await user.type(screen.getByLabelText('Password'), 'Password1!')
    await user.click(screen.getByRole('button', { name: 'Log in' }))
    await waitFor(() => expect(screen.getByText('Tool page')).toBeInTheDocument())
  })
})
