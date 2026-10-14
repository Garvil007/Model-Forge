import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SizeEstimate } from './SizeEstimate'
import { formatBytes } from './sizeEstimateFormulas'
import type { ModelInfo } from './types'

const MODEL: ModelInfo = {
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 1e6,
  size: 1_000_000,
}

describe('formatBytes', () => {
  it('formats across units', () => {
    expect(formatBytes(500)).toBe('500 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(5_242_880)).toBe('5.0 MB')
    expect(formatBytes(2_147_483_648)).toBe('2.00 GB')
  })
})

describe('SizeEstimate', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('shows the estimated output and percentage smaller', () => {
    render(<SizeEstimate operationId="q_fp16" model={MODEL} values={{}} />)
    act(() => vi.runAllTimers())
    expect(screen.getByText(/Estimated output:/)).toBeInTheDocument()
    expect(screen.getByText(/50% smaller/)).toBeInTheDocument()
  })

  it('falls back to a generic message when the size cannot be estimated', () => {
    render(<SizeEstimate operationId="d_logit" model={MODEL} values={{ student: 'custom' }} />)
    act(() => vi.runAllTimers())
    expect(screen.getByText('Estimated output: depends on your student model.')).toBeInTheDocument()
  })

  it('debounces recomputation while values change rapidly', () => {
    const { rerender } = render(
      <SizeEstimate
        operationId="p_magnitude"
        model={MODEL}
        values={{ storage: 'sparse', sparsity: 10 }}
      />,
    )
    act(() => vi.runAllTimers())
    rerender(
      <SizeEstimate
        operationId="p_magnitude"
        model={MODEL}
        values={{ storage: 'sparse', sparsity: 90 }}
      />,
    )
    // immediately after the change, the debounced value hasn't updated yet
    expect(screen.queryByText(/90/)).not.toBeInTheDocument()
    act(() => vi.runAllTimers())
    expect(screen.getByText(/Estimated output:/)).toBeInTheDocument()
  })
})
