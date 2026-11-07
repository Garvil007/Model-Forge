import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ApiJob, ApiModel } from '../../api/types'
import { JobHistoryTable } from './JobHistoryTable'

const meta: Meta<typeof JobHistoryTable> = {
  title: 'Dashboard/JobHistoryTable',
  component: JobHistoryTable,
  args: { onRerun: () => {} },
}

export default meta
type Story = StoryObj<typeof JobHistoryTable>

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

const JOBS: ApiJob[] = [
  {
    id: 'job_1',
    modelId: 'model_1',
    operationId: 'q_int8_static',
    values: {},
    status: 'succeeded',
    stages: [],
    createdAt: '2026-10-21T10:00:00.000Z',
    result: {
      outputBytes: 26_000_000,
      downloadName: 'resnet50_int8.onnx',
      metrics: { 'Top-1 accuracy': '75.8% (was 76.1%)' },
      measuredOnValidation: true,
      speedNote: null,
    },
    error: null,
    cost: 0.03,
  },
  {
    id: 'job_2',
    modelId: 'model_1',
    operationId: 'p_structured',
    values: {},
    status: 'failed',
    stages: [],
    createdAt: '2026-10-22T10:00:00.000Z',
    result: null,
    error: { code: 'out_of_memory', message: 'Ran out of memory.' },
    cost: 0.01,
  },
]

export const Full: Story = { args: { jobs: JOBS, models: [MODEL] } }
export const Empty: Story = { args: { jobs: [], models: [] } }
export const Loading: Story = { args: { jobs: [], models: [], isLoading: true } }
export const ErrorState: Story = { args: { jobs: [], models: [], isError: true } }
export const WithPagination: Story = {
  args: { jobs: JOBS, models: [MODEL], hasNextPage: true },
}
export const WithCompareSelection: Story = {
  args: {
    jobs: JOBS,
    models: [MODEL],
    selectedIds: new Set(['job_1']),
    onToggleSelect: () => {},
  },
}
