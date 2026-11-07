import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ApiJob, ApiModel } from '../../api/types'
import { JobHistoryTable } from './JobHistoryTable'

const MODEL: ApiModel = {
  id: 'model_1',
  filename: 'resnet50.onnx',
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25_600_000,
  size: 100_000_000,
  inputs: null,
  metric: null,
  validationFilename: null,
  source: 'upload',
  repoId: null,
  createdAt: '2026-10-20T10:00:00.000Z',
}

const SUCCEEDED_JOB: ApiJob = {
  id: 'job_1',
  modelId: 'model_1',
  operationId: 'q_int8_static',
  values: {},
  status: 'succeeded',
  stages: [],
  createdAt: '2026-10-21T10:00:00.000Z',
  result: {
    outputBytes: 25_000_000,
    downloadName: 'resnet50_int8.onnx',
    metrics: { 'Top-1 accuracy': '75.8% (was 76.1%)' },
    measuredOnValidation: true,
    speedNote: null,
  },
  error: null,
  cost: 0.03,
}

describe('JobHistoryTable', () => {
  it('shows an empty state when there are no jobs', () => {
    render(<JobHistoryTable jobs={[]} models={[]} onRerun={vi.fn()} />)
    expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument()
  })

  it('shows a loading skeleton while the query is pending', () => {
    render(<JobHistoryTable jobs={[]} models={[]} isLoading onRerun={vi.fn()} />)
    expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(1)
  })

  it('shows an error notice when the query fails', () => {
    render(<JobHistoryTable jobs={[]} models={[]} isError onRerun={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load/i)
  })

  it('shows size change, accuracy change and cost for a succeeded job', () => {
    render(<JobHistoryTable jobs={[SUCCEEDED_JOB]} models={[MODEL]} onRerun={vi.fn()} />)
    expect(screen.getByText('75% smaller')).toBeInTheDocument()
    expect(screen.getByText('75.8% (was 76.1%)')).toBeInTheDocument()
    expect(screen.getByText('$0.03')).toBeInTheDocument()
  })

  it('shows a dash for size/accuracy change on a job with no result yet', () => {
    const queued: ApiJob = { ...SUCCEEDED_JOB, status: 'queued', result: null }
    render(<JobHistoryTable jobs={[queued]} models={[MODEL]} onRerun={vi.fn()} />)
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('calls onRerun with the job when "Re-run" is clicked', async () => {
    const onRerun = vi.fn()
    render(<JobHistoryTable jobs={[SUCCEEDED_JOB]} models={[MODEL]} onRerun={onRerun} />)
    await userEvent.click(screen.getByRole('button', { name: 'Re-run' }))
    expect(onRerun).toHaveBeenCalledWith(SUCCEEDED_JOB)
  })

  it('shows a compare checkbox only for succeeded jobs, and toggles selection', async () => {
    const onToggleSelect = vi.fn()
    const failed: ApiJob = { ...SUCCEEDED_JOB, id: 'job_2', status: 'failed', result: null }
    render(
      <JobHistoryTable
        jobs={[SUCCEEDED_JOB, failed]}
        models={[MODEL]}
        onRerun={vi.fn()}
        onToggleSelect={onToggleSelect}
        selectedIds={new Set()}
      />,
    )
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(1)
    await userEvent.click(checkboxes[0])
    expect(onToggleSelect).toHaveBeenCalledWith(SUCCEEDED_JOB)
  })

  it('shows a "Load more" button when hasNextPage is true', async () => {
    const onLoadMore = vi.fn()
    render(
      <JobHistoryTable
        jobs={[SUCCEEDED_JOB]}
        models={[MODEL]}
        onRerun={vi.fn()}
        hasNextPage
        onLoadMore={onLoadMore}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(onLoadMore).toHaveBeenCalledOnce()
  })
})
