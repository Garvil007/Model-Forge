import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Range } from './Range'

describe('Range', () => {
  it('shows the current value with its unit in the output', () => {
    render(<Range label="Sparsity" min={10} max={95} step={5} defaultValue={50} unit="%" />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('updates the readout when the slider changes', () => {
    render(<Range label="Sparsity" min={10} max={95} step={5} defaultValue={50} unit="%" />)
    const slider = screen.getByLabelText('Sparsity')
    fireEvent.input(slider, { target: { value: '70' } })
    expect(screen.getByText('70%')).toBeInTheDocument()
  })
})
