import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { ThemeProvider } from './ui/theme/ThemeProvider'
import { ToastProvider } from './ui/toast/ToastProvider'

function renderApp(initialPath = '/') {
  const queryClient = new QueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[initialPath]}>
            <AuthProvider>
              <App />
            </AuthProvider>
          </MemoryRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

describe('App', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('renders the landing page at /', async () => {
    renderApp('/')
    expect(
      await screen.findByRole('heading', { name: /Compress and convert any model/ }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ModelForge' })).toBeInTheDocument()
  })

  it('redirects an unauthenticated visitor from /app to /login', async () => {
    renderApp('/app')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument())
  })

  it('renders a 404 page for unknown routes', async () => {
    renderApp('/nope')
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
