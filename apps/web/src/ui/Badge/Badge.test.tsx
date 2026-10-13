import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Badge } from './Badge'

describe('Badge', () => {
  it('shows the accuracy copy for each variant', () => {
    render(<Badge variant="lossless" />)
    expect(screen.getByText('No accuracy change')).toBeInTheDocument()
  })

  it('renders the near-lossless and lossy variants', () => {
    render(
      <>
        <Badge variant="near-lossless" />
        <Badge variant="lossy" />
      </>,
    )
    expect(screen.getByText('Tiny accuracy change')).toBeInTheDocument()
    expect(screen.getByText('Some accuracy loss')).toBeInTheDocument()
  })
})
