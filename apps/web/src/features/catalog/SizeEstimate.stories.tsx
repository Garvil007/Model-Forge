import type { Meta, StoryObj } from '@storybook/react-vite'
import { SizeEstimate } from './SizeEstimate'
import type { ModelInfo } from './types'

const meta: Meta<typeof SizeEstimate> = {
  title: 'Catalog/SizeEstimate',
  component: SizeEstimate,
}

export default meta
type Story = StoryObj<typeof SizeEstimate>

const MODEL: ModelInfo = {
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25.6e6,
  size: 102_442_450,
}

export const Smaller: Story = {
  render: () => <SizeEstimate operationId="q_fp16" model={MODEL} values={{}} />,
}

export const SameSize: Story = {
  render: () => <SizeEstimate operationId="c_onnx" model={MODEL} values={{}} />,
}

export const UnknownSize: Story = {
  name: 'Unknown size (custom student)',
  render: () => <SizeEstimate operationId="d_logit" model={MODEL} values={{ student: 'custom' }} />,
}
