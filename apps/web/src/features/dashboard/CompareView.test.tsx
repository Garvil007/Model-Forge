import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ApiJob, ApiModel } from '../../api/types'
import { CompareView } from './CompareView'

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

function succeededJob(id: string, operationId: string, outputBytes: number): ApiJob {
  return {
    id,
    modelId: 'model_1',
    operationId,
    values: {},
    status: 'succeeded',
    stages: [],
    createdAt: '2026-10-21T10:00:00.000Z',
    result: {
      outputBytes,
      downloadName: 'out.onnx',
      metrics: { 'Top-1 accuracy': '75.8% (was 76.1%)' },
      measuredOnValidation: true,
      speedNote: 'about 2x faster',
    },
    error: null,
    cost: 0.03,
  }
}

describe('CompareView', () => {
  it('asks for at least two results when there are none', () => {
    render(<CompareView model={MODEL} jobs={[]} />)
    expect(screen.getByText(/pick at least two/i)).toBeInTheDocument()
  })

  it('asks for at least two results when only one succeeded job is picked', () => {
    render(
      <CompareView model={MODEL} jobs={[succeededJob('job_1', 'q_int8_static', 26_000_000)]} />,
    )
    expect(screen.getByText(/pick at least two/i)).toBeInTheDocument()
  })

  it('renders size, accuracy and latency for every comparable job', () => {
    const jobs = [
      succeededJob('job_1', 'q_int8_static', 26_000_000),
      succeededJob('job_2', 'p_structured', 60_000_000),
    ]
    render(<CompareView model={MODEL} jobs={jobs} />)
    expect(screen.getAllByText(/75\.8% \(was 76\.1%\)/)).toHaveLength(2)
    expect(screen.getAllByText('about 2x faster')).toHaveLength(2)
    expect(screen.getByText('74% smaller')).toBeInTheDocument()
    expect(screen.getByText('40% smaller')).toBeInTheDocument()
  })

  it('ignores a failed job even when picked', () => {
    const jobs = [
      succeededJob('job_1', 'q_int8_static', 26_000_000),
      succeededJob('job_2', 'p_structured', 60_000_000),
      { ...succeededJob('job_3', 'q_gguf', 10_000_000), status: 'failed' as const, result: null },
    ]
    render(<CompareView model={MODEL} jobs={jobs} />)
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2 comparable jobs
  })
})
