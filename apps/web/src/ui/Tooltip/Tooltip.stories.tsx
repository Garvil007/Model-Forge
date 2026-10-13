import type { Meta, StoryObj } from '@storybook/react-vite'
import { Tooltip } from './Tooltip'

const meta: Meta<typeof Tooltip> = {
  title: 'UI/Tooltip',
  component: Tooltip,
}

export default meta
type Story = StoryObj<typeof Tooltip>

export const Default: Story = {
  render: () => (
    <Tooltip label="Higher values soften the teacher's outputs so the student learns more from its near-misses.">
      <button type="button">Temperature</button>
    </Tooltip>
  ),
}
