import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { DashboardPage } from './DashboardPage'

describe('DashboardPage', () => {
  it('shows an empty state linking to the tool', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('No models yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Upload a model' })).toHaveAttribute('href', '/app')
  })
})
