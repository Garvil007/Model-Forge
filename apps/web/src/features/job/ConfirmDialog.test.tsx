import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('shows the meta facts and confirms', async () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        title="This job runs on a GPU / takes a while"
        body="Running this will cost real money."
        meta={['Estimated time: 10 minutes', 'Estimated cost: $1.00']}
        confirmLabel="Start job"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText('Estimated time: 10 minutes')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /start job/i }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('cancels on Escape', async () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Cancel this job?"
        body="Progress will be discarded."
        confirmLabel="Cancel job"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    )
    await userEvent.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
