import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { authProvider } from '../auth/provider'
import { AuthProvider } from '../auth/AuthProvider'
import { ToastProvider } from '../ui/toast/ToastProvider'
import { SettingsPage } from './SettingsPage'

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter>
          <AuthProvider>
            <SettingsPage />
          </AuthProvider>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('SettingsPage', () => {
  beforeEach(async () => {
    localStorage.clear()
    await authProvider.signUp('settings@user.com', 'Password1!')
    await authProvider.confirmSignUp('settings@user.com', '123456')
  })
  afterEach(() => localStorage.clear())

  it('shows the signed-in user email', async () => {
    renderSettings()
    await waitFor(() =>
      expect(screen.getByText('Signed in as settings@user.com.')).toBeInTheDocument(),
    )
  })

  it('loads and toggles notification settings', async () => {
    renderSettings()
    const toggle = await screen.findByLabelText('Email me when a job finishes')
    expect(toggle).toBeChecked()
    await userEvent.click(toggle)
    await waitFor(() => expect(toggle).not.toBeChecked())
  })

  it('saves a Hugging Face token and then offers to remove it', async () => {
    renderSettings()
    expect(await screen.findByText(/no token on file/i)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Access token'), 'hf_test_token')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/a token is on file/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
  })

  it('only enables account deletion once DELETE is typed exactly', async () => {
    renderSettings()
    const deleteButton = screen.getByRole('button', { name: 'Delete my account' })
    expect(deleteButton).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'delete')
    expect(deleteButton).toBeDisabled()
    await userEvent.clear(screen.getByLabelText('Type DELETE to confirm'))
    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE')
    expect(deleteButton).toBeEnabled()
  })
})
