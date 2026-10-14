import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { RunButton } from './RunButton'

describe('RunButton', () => {
  it('renders the given label and calls onClick', async () => {
    const onClick = vi.fn()
    render(
      <RunButton
        label="Compress with FP16 weights"
        disabled={false}
        running={false}
        onClick={onClick}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: /compress with fp16 weights/i }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('is disabled while a job runs', () => {
    render(
      <RunButton
        label="Compress with FP16 weights"
        disabled={true}
        running={true}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
