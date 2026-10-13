import type { Meta, StoryObj } from '@storybook/react-vite'
import { NumberInput } from './NumberInput'

const meta: Meta<typeof NumberInput> = {
  title: 'UI/NumberInput',
  component: NumberInput,
  args: { label: 'Fine-tuning epochs', defaultValue: 3, min: 1, max: 100 },
}

export default meta
type Story = StoryObj<typeof NumberInput>

export const Default: Story = {}
export const Disabled: Story = { args: { disabled: true } }
