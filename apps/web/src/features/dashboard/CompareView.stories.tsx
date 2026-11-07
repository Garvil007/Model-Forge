import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ApiJob, ApiModel } from '../../api/types'
import { CompareView } from './CompareView'

const meta: Meta<typeof CompareView> = {
  title: 'Dashboard/CompareView',
  component: CompareView,
}

export default meta
type Story = StoryObj<typeof CompareView>

const MODEL: ApiModel = {
  id: 'model_1',
  filename: 'resnet50.onnx',
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25_600_000,
  size: 100_000_000,
  inputs: null,
  metric: ['Top-1 accuracy', 76.1, '%'],
  validationFilename: null,
  source: 'upload',
  repoId: null,
  createdAt: '2026-10-20T10:00:00.000Z',
}

function succeededJob(
  id: string,
  operationId: string,
  outputBytes: number,
  accuracy: string,
): ApiJob {
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
      downloadName: `resnet50_${operationId}.onnx`,
      metrics: { 'Top-1 accuracy': accuracy },
      measuredOnValidation: true,
      speedNote: 'about 2 to 3 times faster on CPU',
    },
    error: null,
    cost: 0.03,
  }
}

const JOBS: ApiJob[] = [
  succeededJob('job_1', 'q_int8_static', 26_000_000, '75.8% (was 76.1%)'),
  succeededJob('job_2', 'q_int8_dyn', 30_000_000, '76.0% (was 76.1%)'),
  succeededJob('job_3', 'p_structured', 60_000_000, '74.9% (was 76.1%)'),
]

export const Full: Story = { args: { model: MODEL, jobs: JOBS } }
export const NeedsMoreResults: Story = { args: { model: MODEL, jobs: [JOBS[0]] } }
export const Empty: Story = { args: { model: MODEL, jobs: [] } }
