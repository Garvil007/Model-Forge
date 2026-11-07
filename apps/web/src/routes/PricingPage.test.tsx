import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PricingPage } from './PricingPage'

function renderPricingPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PricingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PricingPage', () => {
  it('renders Free and Pro from /billing/plans', async () => {
    renderPricingPage()

    // "$0" only appears on the loaded plan card, unlike "Free" (also in the static
    // workings table below) — waiting on it proves the real fetch resolved.
    await screen.findByText('$0')
    expect(screen.getByRole('heading', { name: 'Free' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Pro' })).toBeInTheDocument()
    expect(screen.getByText('$29/mo')).toBeInTheDocument()
  })

  it('shows the cost-derivation workings', async () => {
    renderPricingPage()

    await screen.findByText('$0')
    expect(screen.getByText('How we priced this')).toBeInTheDocument()
  })
})
