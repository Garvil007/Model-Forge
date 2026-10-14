import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ToastProvider } from '../ui/toast/ToastProvider'
import { AuthProvider } from './AuthProvider'
import { useAuth } from './useAuth'

function Probe() {
  const { user, isLoading, signUp, confirmSignUp, signIn, signOut, expireSession } = useAuth()
  return (
    <div>
      <p data-testid="status">{isLoading ? 'loading' : user ? `in:${user.email}` : 'out'}</p>
      <button onClick={() => signUp('a@b.com', 'Password1!')}>signup</button>
      <button onClick={() => confirmSignUp('a@b.com', '123456')}>confirm</button>
      <button onClick={() => signIn('a@b.com', 'Password1!')}>signin</button>
      <button onClick={() => signOut()}>signout</button>
      <button onClick={() => expireSession()}>expire</button>
    </div>
  )
}

function renderProbe() {
  render(
    <ToastProvider>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </ToastProvider>,
  )
}

describe('AuthProvider', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('signs up, confirms, and signs out', async () => {
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('out'))

    await act(async () => screen.getByText('signup').click())
    await act(async () => screen.getByText('confirm').click())
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('in:a@b.com'))

    await act(async () => screen.getByText('signout').click())
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('out'))
  })

  it('shows a toast and clears the user on session expiry', async () => {
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('out'))
    await act(async () => screen.getByText('expire').click())
    expect(screen.getByText('Your session expired. Please log in again.')).toBeInTheDocument()
  })
})
