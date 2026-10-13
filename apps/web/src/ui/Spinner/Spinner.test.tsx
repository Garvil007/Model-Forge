import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Spinner } from './Spinner'

describe('Spinner', () => {
  it('exposes a status role for assistive tech', () => {
    render(<Spinner label="Running job" />)
    expect(screen.getByRole('status', { name: 'Running job' })).toBeInTheDocument()
  })
})
