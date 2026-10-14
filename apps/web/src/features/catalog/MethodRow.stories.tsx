import type { Meta, StoryObj } from '@storybook/react-vite'
import { MethodRow } from './MethodRow'
import type { Operation } from './types'

const meta: Meta<typeof MethodRow> = {
  title: 'Catalog/MethodRow',
  component: MethodRow,
  decorators: [(Story) => <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>{Story()}</ul>],
}

export default meta
type Story = StoryObj<typeof MethodRow>

const OPERATION: Operation = {
  id: 'q_fp16',
  technique: 'quantization',
  label: 'FP16 (half precision)',
  description: 'Stores weights as 16-bit floats. The safest first step for any model.',
  accuracy: 'near-lossless',
  typicalImpact: 'under 0.1% accuracy change',
  timeEstimate: 'seconds',
  sourceFormats: ['onnx'],
  workerImage: 'cpu-base',
  queue: 'cpu',
}

export const Available: Story = {
  args: { operation: OPERATION, availability: { ok: true }, selected: false, onSelect: () => {} },
}

export const Selected: Story = {
  args: { operation: OPERATION, availability: { ok: true }, selected: true, onSelect: () => {} },
}

export const Disabled: Story = {
  args: {
    operation: OPERATION,
    availability: { ok: false, why: 'Not available for safetensors. Works with ONNX.' },
    selected: false,
    onSelect: () => {},
  },
}
