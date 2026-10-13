import type { Meta, StoryObj } from '@storybook/react-vite'
import { Badge } from './Badge'

const meta: Meta<typeof Badge> = {
  title: 'UI/Badge',
  component: Badge,
}

export default meta
type Story = StoryObj<typeof Badge>

export const Lossless: Story = { args: { variant: 'lossless' } }
export const NearLossless: Story = { args: { variant: 'near-lossless' } }
export const Lossy: Story = { args: { variant: 'lossy' } }
