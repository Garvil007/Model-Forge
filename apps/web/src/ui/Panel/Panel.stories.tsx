import type { Meta, StoryObj } from '@storybook/react-vite'
import { Panel } from './Panel'

const meta: Meta<typeof Panel> = {
  title: 'UI/Panel',
  component: Panel,
}

export default meta
type Story = StoryObj<typeof Panel>

export const Default: Story = {
  args: { children: 'Panel content' },
}
