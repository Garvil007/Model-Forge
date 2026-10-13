import type { Meta, StoryObj } from '@storybook/react-vite'
import { Chip } from './Chip'

const meta: Meta<typeof Chip> = {
  title: 'UI/Chip',
  component: Chip,
  args: { children: 'ResNet-50 (ONNX)' },
}

export default meta
type Story = StoryObj<typeof Chip>

export const Default: Story = {}
