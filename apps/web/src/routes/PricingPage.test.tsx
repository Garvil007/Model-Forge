import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PricingPage } from './PricingPage'

describe('PricingPage', () => {
  it('renders all three plans', () => {
    render(
      <MemoryRouter>
        <PricingPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('Free')).toBeInTheDocument()
    expect(screen.getByText('Pro')).toBeInTheDocument()
    expect(screen.getByText('Team')).toBeInTheDocument()
  })
})
