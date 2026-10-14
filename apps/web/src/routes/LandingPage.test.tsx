import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { LandingPage } from './LandingPage'

describe('LandingPage', () => {
  it('renders the hero, technique table, and call to action', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('heading', { name: /Compress and convert any model/ }),
    ).toBeInTheDocument()
    expect(screen.getByRole('radiogroup', { name: 'Compression technique' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How it works' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start compressing for free' })).toBeInTheDocument()
  })
})
