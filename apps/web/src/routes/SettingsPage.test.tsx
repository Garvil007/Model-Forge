import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { authProvider } from '../auth/provider'
import { AuthProvider } from '../auth/AuthProvider'
import { ToastProvider } from '../ui/toast/ToastProvider'
import { SettingsPage } from './SettingsPage'

describe('SettingsPage', () => {
  beforeEach(async () => {
    localStorage.clear()
    await authProvider.signUp('settings@user.com', 'Password1!')
    await authProvider.confirmSignUp('settings@user.com', '123456')
  })
  afterEach(() => localStorage.clear())

  it('shows the signed-in user email', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <AuthProvider>
            <SettingsPage />
          </AuthProvider>
        </MemoryRouter>
      </ToastProvider>,
    )
    await waitFor(() =>
      expect(screen.getByText('Signed in as settings@user.com.')).toBeInTheDocument(),
    )
  })
})
