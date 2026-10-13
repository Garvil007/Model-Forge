import type { Meta, StoryObj } from '@storybook/react-vite'
import { Range } from './Range'

const meta: Meta<typeof Range> = {
  title: 'UI/Range',
  component: Range,
  args: { label: 'Sparsity', min: 10, max: 95, step: 5, defaultValue: 50, unit: '%' },
}

export default meta
type Story = StoryObj<typeof Range>

export const Default: Story = {}
export const WithHelp: Story = {
  args: {
    label: 'Temperature',
    min: 1,
    max: 10,
    step: 0.5,
    defaultValue: 4,
    unit: '',
    help: "Higher values soften the teacher's outputs so the student learns more from its near-misses.",
  },
}
