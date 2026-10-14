import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { JobError } from './JobError'

describe('JobError', () => {
  it('names the unsupported operator and never shows a raw stack trace', () => {
    render(
      <JobError
        error={{
          code: 'unsupported_operator',
          operator: 'aten::flash_attn',
          message:
            "This model uses the operator aten::flash_attn, which this conversion target doesn't support yet.",
        }}
      />,
    )
    expect(screen.getByText(/aten::flash_attn/)).toBeInTheDocument()
    expect(screen.queryByText(/at\s+\w+\s*\(/)).not.toBeInTheDocument()
  })

  it('offers a same-settings retry only for a spot interruption', async () => {
    const onRetry = vi.fn()
    render(
      <JobError error={{ code: 'spot_interrupted', message: 'Reclaimed.' }} onRetry={onRetry} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /^retry$/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('offers "retry with adjusted settings" for a correctable error, not for quota exceeded', () => {
    const { rerender } = render(
      <JobError
        error={{ code: 'out_of_memory', message: 'Ran out of memory.' }}
        onAdjustSettings={vi.fn()}
      />,
    )
    expect(
      screen.getByRole('button', { name: /retry with adjusted settings/i }),
    ).toBeInTheDocument()

    rerender(
      <JobError
        error={{ code: 'quota_exceeded', message: 'Quota used up.' }}
        onAdjustSettings={vi.fn()}
      />,
    )
    expect(
      screen.queryByRole('button', { name: /retry with adjusted settings/i }),
    ).not.toBeInTheDocument()
  })
})
