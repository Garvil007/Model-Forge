import type { Meta, StoryObj } from '@storybook/react-vite'
import { ModelDropzone } from './ModelDropzone'

const meta: Meta<typeof ModelDropzone> = {
  title: 'Model/ModelDropzone',
  component: ModelDropzone,
}
export default meta
type Story = StoryObj<typeof ModelDropzone>

const noop = () => {}

export const Default: Story = {
  args: { onFile: noop, onSample: noop },
}

export const Busy: Story = {
  args: { onFile: noop, onSample: noop, disabled: true },
}
