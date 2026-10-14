import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { JobStage } from '../../api/types'
import { JobProgress } from './JobProgress'

const stages: JobStage[] = [
  { label: 'Loading teacher', status: 'done' },
  { label: 'Building student', status: 'done' },
  { label: 'Training student', status: 'active', epoch: 17, totalEpochs: 40 },
  { label: 'Measuring accuracy', status: 'pending' },
]

describe('JobProgress', () => {
  it('shows each stage label and the current epoch of the active training stage', () => {
    render(
      <JobProgress stages={stages} elapsedSeconds={185} reconnecting={false} onCancel={vi.fn()} />,
    )
    expect(screen.getByText('Training student')).toBeInTheDocument()
    expect(screen.getByText('epoch 17 of 40')).toBeInTheDocument()
    expect(screen.getByText('Elapsed: 3m 5s')).toBeInTheDocument()
  })

  it('shows a reconnecting notice when polling has dropped', () => {
    render(<JobProgress stages={stages} elapsedSeconds={0} reconnecting onCancel={vi.fn()} />)
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument()
  })

  it('calls onCancel when the cancel button is clicked', async () => {
    const onCancel = vi.fn()
    render(
      <JobProgress stages={stages} elapsedSeconds={0} reconnecting={false} onCancel={onCancel} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /cancel job/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
