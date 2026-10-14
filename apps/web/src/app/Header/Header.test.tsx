import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../../auth/AuthProvider'
import { ThemeProvider } from '../../ui/theme/ThemeProvider'
import { ToastProvider } from '../../ui/toast/ToastProvider'
import { Header } from './Header'

function renderHeader() {
  render(
    <ThemeProvider>
      <ToastProvider>
        <MemoryRouter>
          <AuthProvider>
            <Header />
          </AuthProvider>
        </MemoryRouter>
      </ToastProvider>
    </ThemeProvider>,
  )
}

describe('Header', () => {
  it('renders the logo, nav links, and theme toggle', () => {
    renderHeader()
    expect(screen.getByRole('link', { name: 'ModelForge' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Tool' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Pricing' })).toBeInTheDocument()
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeInTheDocument()
  })
})
