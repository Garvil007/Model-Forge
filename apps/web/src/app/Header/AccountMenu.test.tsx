import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { authProvider } from '../../auth/provider'
import { AuthProvider } from '../../auth/AuthProvider'
import { ToastProvider } from '../../ui/toast/ToastProvider'
import { AccountMenu } from './AccountMenu'

function renderMenu() {
  render(
    <ToastProvider>
      <MemoryRouter>
        <AuthProvider>
          <AccountMenu />
        </AuthProvider>
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('AccountMenu', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('shows a log in link when signed out', async () => {
    renderMenu()
    await waitFor(() => expect(screen.getByRole('link', { name: 'Log in' })).toBeInTheDocument())
  })

  it('shows account options when signed in', async () => {
    await authProvider.signUp('menu@test.com', 'Password1!')
    await authProvider.confirmSignUp('menu@test.com', '123456')
    renderMenu()

    const trigger = await screen.findByRole('button', { name: 'menu@test.com' })
    const user = userEvent.setup()
    await act(async () => user.click(trigger))
    expect(screen.getByRole('menuitem', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Log out' })).toBeInTheDocument()
  })
})
