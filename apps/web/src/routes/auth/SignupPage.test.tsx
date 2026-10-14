import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AuthProvider } from '../../auth/AuthProvider'
import { ToastProvider } from '../../ui/toast/ToastProvider'
import { SignupPage } from './SignupPage'

function renderPage() {
  render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/signup']}>
        <AuthProvider>
          <Routes>
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/verify" element={<p>Verify page</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('SignupPage', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('shows a strength hint as the password is typed', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/^Password/), 'Str0ng!Password')
    expect(screen.getByText('Strength: strong')).toBeInTheDocument()
  })

  it('rejects mismatched passwords', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'new@user.com')
    await user.type(screen.getByLabelText(/^Password/), 'Password1!')
    await user.type(screen.getByLabelText('Confirm password'), 'Different1!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
  })

  it('signs up and navigates to /verify on success', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'new@user.com')
    await user.type(screen.getByLabelText(/^Password/), 'Password1!')
    await user.type(screen.getByLabelText('Confirm password'), 'Password1!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(screen.getByText('Verify page')).toBeInTheDocument())
  })
})
