import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ToastProvider } from '../ui/toast/ToastProvider'
import { AuthProvider } from './AuthProvider'
import { RouteGuard } from './RouteGuard'

function renderGuarded(initialPath: string) {
  render(
    <ToastProvider>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/login" element={<p>Login page</p>} />
            <Route
              path="/dashboard"
              element={
                <RouteGuard>
                  <p>Dashboard content</p>
                </RouteGuard>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </ToastProvider>,
  )
}

describe('RouteGuard', () => {
  it('redirects an unauthenticated visitor to /login', async () => {
    renderGuarded('/dashboard')
    await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument())
  })
})
