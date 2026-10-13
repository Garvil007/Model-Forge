import type { Meta, StoryObj } from '@storybook/react-vite'
import { Skeleton } from './Skeleton'

const meta: Meta<typeof Skeleton> = {
  title: 'UI/Skeleton',
  component: Skeleton,
}

export default meta
type Story = StoryObj<typeof Skeleton>

export const Line: Story = { args: { width: '240px', height: '16px' } }
export const Block: Story = { args: { width: '100%', height: '80px' } }
