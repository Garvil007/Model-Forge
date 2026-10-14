import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/AuthProvider'
import { ThemeProvider } from '../ui/theme/ThemeProvider'
import { ToastProvider } from '../ui/toast/ToastProvider'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders a skip link and the routed page content', () => {
    render(
      <ThemeProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={['/']}>
            <AuthProvider>
              <Routes>
                <Route element={<AppShell />}>
                  <Route path="/" element={<p>Page body</p>} />
                </Route>
              </Routes>
            </AuthProvider>
          </MemoryRouter>
        </ToastProvider>
      </ThemeProvider>,
    )
    expect(screen.getByRole('link', { name: 'Skip to content' })).toBeInTheDocument()
    expect(screen.getByText('Page body')).toBeInTheDocument()
  })
})
