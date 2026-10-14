import type { Meta, StoryObj } from '@storybook/react-vite'
import { RunButton } from './RunButton'

const meta: Meta<typeof RunButton> = {
  title: 'Job/RunButton',
  component: RunButton,
  args: { label: 'Compress with FP16 weights', disabled: false, running: false, onClick: () => {} },
}

export default meta
type Story = StoryObj<typeof RunButton>

export const Ready: Story = {}
export const Running: Story = { args: { running: true, disabled: true } }
export const MissingParam: Story = {
  args: { label: 'Add calibration inputs to continue', disabled: true },
}
export const ConvertLabel: Story = { args: { label: 'Convert to ONNX' } }
export const TrainLabel: Story = { args: { label: 'Train the student model' } }
