import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import type { ApiModel } from '../../api/types'
import { jobs, models } from '../../mocks/db'
import { resetScenarios, setScenarios, type JobErrorScenario } from '../../mocks/scenarios'
import { getOperationById } from '../catalog/types'
import { JobRunner } from './JobRunner'

const resnetModel: ApiModel = {
  id: 'model_resnet',
  filename: 'resnet50.onnx',
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25.6e6,
  size: 102_442_450,
  inputs: 'input [batch, 3, 224, 224]',
  metric: ['Top-1 accuracy (ImageNet val)', 76.1, '%'],
  validationFilename: null,
  source: 'upload',
  repoId: null,
  createdAt: '2026-01-01T00:00:00.000Z',
}

const llamaModel: ApiModel = {
  ...resnetModel,
  id: 'model_llama',
  filename: 'Llama-3.2-1B/model.safetensors',
  format: 'safetensors',
  family: 'llm',
  bits: 16,
}

function renderRunner(model: ApiModel, operationId: string, initialPath = '/') {
  models.set(model.id, model)
  const operation = getOperationById(operationId)!
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <JobRunner tab="compress" model={model} operation={operation} values={{}} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => resetScenarios())

describe('JobRunner', () => {
  it('runs a cheap CPU job end to end and shows the result', async () => {
    renderRunner(resnetModel, 'q_fp16')
    await userEvent.click(screen.getByRole('button', { name: /compress with fp16/i }))

    expect(await screen.findByRole('group', { name: /job progress/i })).toBeInTheDocument()
    expect(
      await screen.findByText(/smaller|larger|same size/i, {}, { timeout: 8000 }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try other settings/i })).toBeInTheDocument()
  }, 15000)

  it('requires confirmation before an expensive GPU job but never for a cheap CPU job', async () => {
    renderRunner(llamaModel, 'q_gptq')
    await userEvent.click(screen.getByRole('button', { name: /compress with/i }))

    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/estimated cost/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/estimated time/i)).toBeInTheDocument()

    // Cancelling the confirmation never creates a job.
    await userEvent.click(within(dialog).getByRole('button', { name: /cancel/i }))
    expect(screen.queryByRole('group', { name: /job progress/i })).not.toBeInTheDocument()
  })

  it('cancels a running job after confirming', async () => {
    renderRunner(resnetModel, 'q_fp16')
    await userEvent.click(screen.getByRole('button', { name: /compress with fp16/i }))
    await screen.findByRole('group', { name: /job progress/i })

    await userEvent.click(screen.getByRole('button', { name: /cancel job/i }))
    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/cancel this job/i)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: /cancel job/i }))

    expect(await screen.findByText(/job canceled/i)).toBeInTheDocument()
  })

  const errorCases: Array<[JobErrorScenario, RegExp]> = [
    ['out_of_memory', /ran out of memory/i],
    ['unsupported_operator', /unsupported operator/i],
    ['bad_calibration_data', /calibration data problem/i],
    ['gated_model', /model access required/i],
    ['spot_interrupted', /instance interrupted/i],
  ]

  it.each(errorCases)(
    'teaches the %s error state without a raw stack trace',
    async (kind, titlePattern) => {
      setScenarios({ jobErrorKind: kind })
      renderRunner(resnetModel, 'q_fp16')
      await userEvent.click(screen.getByRole('button', { name: /compress with fp16/i }))

      const alert = await screen.findByRole('alert', {}, { timeout: 8000 })
      expect(alert.textContent).toMatch(titlePattern)
      expect(alert.textContent).not.toMatch(/at\s+\w+\s*\(/)
    },
    15000,
  )

  it('restores the progress view from the job id in the URL after a reload', async () => {
    renderRunner(resnetModel, 'q_fp16')
    await userEvent.click(screen.getByRole('button', { name: /compress with fp16/i }))
    await screen.findByRole('group', { name: /job progress/i })

    const jobId = [...jobs.keys()].pop()
    expect(jobId).toBeTruthy()

    // Simulate a reload: a brand new app shell (fresh QueryClient, fresh history) that only
    // knows the job id from the URL — the mock backend still has the job's current state.
    const reloaded = renderRunner(resnetModel, 'q_fp16', `/?job=${jobId}`)
    const scoped = within(reloaded.container)
    expect(
      await scoped.findAllByText(/elapsed|smaller|larger|same size/i, {}, { timeout: 8000 }),
    ).not.toHaveLength(0)
    expect(scoped.queryAllByRole('button', { name: /compress with fp16/i })).toHaveLength(0)
  }, 15000)
})
