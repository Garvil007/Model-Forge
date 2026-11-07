import type { Meta, StoryObj } from '@storybook/react-vite'
import { MemoryRouter } from 'react-router-dom'
import type { ApiModel } from '../../api/types'
import { ModelsTable } from './ModelsTable'

const meta: Meta<typeof ModelsTable> = {
  title: 'Dashboard/ModelsTable',
  component: ModelsTable,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
  args: {
    onCompress: () => {},
    onConvert: () => {},
    onDownload: () => {},
    onDelete: () => {},
  },
}

export default meta
type Story = StoryObj<typeof ModelsTable>

const SAMPLE_MODELS: ApiModel[] = [
  {
    id: 'model_1',
    filename: 'resnet50.onnx',
    format: 'onnx',
    family: 'vision',
    bits: 32,
    params: 25_600_000,
    size: 102_400_000,
    inputs: '1x3x224x224',
    metric: ['Top-1 accuracy', 76.1, '%'],
    validationFilename: null,
    source: 'upload',
    repoId: null,
    createdAt: '2026-10-20T10:00:00.000Z',
  },
  {
    id: 'model_2',
    filename: 'llama-3-8b',
    format: 'torch',
    family: 'llm',
    bits: 16,
    params: 8_000_000_000,
    size: 16_000_000_000,
    inputs: null,
    metric: null,
    validationFilename: null,
    source: 'huggingface',
    repoId: 'meta-llama/Llama-3-8B',
    createdAt: '2026-10-25T10:00:00.000Z',
  },
]

export const Full: Story = { args: { models: SAMPLE_MODELS } }
export const Empty: Story = { args: { models: [] } }
export const Loading: Story = { args: { models: [], isLoading: true } }
export const ErrorState: Story = { args: { models: [], isError: true } }
