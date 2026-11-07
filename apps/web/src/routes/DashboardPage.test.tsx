import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { ApiModel } from '../api/types'
import { jobs, models, type JobRecord } from '../mocks/db'
import { DashboardPage } from './DashboardPage'

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

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

function succeededJob(id: string): JobRecord {
  return {
    id,
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
    startedAt: Date.now(),
    canceled: false,
    stageDefs: [],
  }
}

describe('DashboardPage', () => {
  it('shows an empty state linking to the tool', async () => {
    renderDashboard()
    expect(await screen.findByText('No models yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Upload a model' })).toHaveAttribute('href', '/app')
  })

  it('lists models and switches to the job history tab', async () => {
    models.set(MODEL.id, MODEL)
    jobs.set('job_1', succeededJob('job_1'))
    renderDashboard()

    expect(await screen.findByText('resnet50.onnx')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Job history' }))
    expect(await screen.findByRole('table', { name: 'Job history' })).toHaveTextContent(
      'INT8 static (calibrated)',
    )
  })

  it('shows the compare prompt until two succeeded jobs are selected', async () => {
    models.set(MODEL.id, MODEL)
    jobs.set('job_1', succeededJob('job_1'))
    jobs.set('job_2', succeededJob('job_2'))
    renderDashboard()

    await userEvent.click(screen.getByRole('tab', { name: 'Job history' }))
    await screen.findAllByText('resnet50.onnx')
    const checkboxes = await screen.findAllByRole('checkbox')
    await userEvent.click(checkboxes[0])
    await userEvent.click(checkboxes[1])

    await userEvent.click(screen.getByRole('tab', { name: 'Compare' }))
    await waitFor(() => expect(screen.getByText('Size reduction')).toBeInTheDocument())
  })
})
