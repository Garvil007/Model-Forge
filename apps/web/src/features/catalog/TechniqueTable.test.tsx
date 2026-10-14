import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TechniqueTable } from './TechniqueTable'
import type { Technique } from './types'

const TECHNIQUES: Technique[] = [
  {
    id: 'quantization',
    name: 'Quantization',
    tag: 'Fewer bits per weight',
    mechanism: 'Lowers bit-precision',
    hardwareImpact: 'Drops RAM',
    complexity: 'Low',
    bars: [1, 0.5, 0],
  },
  {
    id: 'pruning',
    name: 'Pruning',
    tag: 'Remove weights',
    mechanism: 'Deletes weights',
    hardwareImpact: 'Shrinks file',
    complexity: 'Medium',
    bars: [1, 1, 0],
  },
  {
    id: 'distillation',
    name: 'Knowledge distillation',
    tag: 'Train a smaller copy',
    mechanism: 'Trains a student',
    hardwareImpact: 'Native, lightweight',
    complexity: 'High',
    bars: [1, 1, 1],
  },
]

describe('TechniqueTable', () => {
  it('renders a radiogroup with one radio per technique, the active one checked', () => {
    render(<TechniqueTable techniques={TECHNIQUES} value="pruning" onChange={vi.fn()} />)
    expect(screen.getByRole('radiogroup')).toBeInTheDocument()
    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(3)
    expect(screen.getByRole('radio', { name: /Pruning/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /Quantization/ })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('selects on click', async () => {
    const onChange = vi.fn()
    render(<TechniqueTable techniques={TECHNIQUES} value="quantization" onChange={onChange} />)
    await userEvent.click(screen.getByRole('radio', { name: /Pruning/ }))
    expect(onChange).toHaveBeenCalledWith('pruning')
  })

  it('moves selection with arrow keys and wraps around', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TechniqueTable techniques={TECHNIQUES} value="distillation" onChange={onChange} />)
    screen.getByRole('radio', { name: /Knowledge distillation/ }).focus()
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith('quantization')
  })

  it('selects the focused technique with Space', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TechniqueTable techniques={TECHNIQUES} value="quantization" onChange={onChange} />)
    screen.getByRole('radio', { name: /Pruning/ }).focus()
    await user.keyboard(' ')
    expect(onChange).toHaveBeenCalledWith('pruning')
  })
})
