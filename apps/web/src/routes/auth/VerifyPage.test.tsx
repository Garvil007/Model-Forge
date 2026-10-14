import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { authProvider } from '../../auth/provider'
import { AuthProvider } from '../../auth/AuthProvider'
import { ToastProvider } from '../../ui/toast/ToastProvider'
import { VerifyPage } from './VerifyPage'

function renderPage() {
  render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/verify?email=new@user.com']}>
        <AuthProvider>
          <Routes>
            <Route path="/verify" element={<VerifyPage />} />
            <Route path="/app" element={<p>Tool page</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('VerifyPage', () => {
  beforeEach(async () => {
    localStorage.clear()
    await authProvider.signUp('new@user.com', 'Password1!')
  })
  afterEach(() => localStorage.clear())

  it('shows an error for the wrong code', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Verification code'), '000000')
    await user.click(screen.getByRole('button', { name: 'Verify' }))
    expect(await screen.findByText(/That code is incorrect/)).toBeInTheDocument()
  })

  it('verifies and navigates to /app on success', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Verification code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Verify' }))
    await waitFor(() => expect(screen.getByText('Tool page')).toBeInTheDocument())
  })
})
