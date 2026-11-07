import type { Meta, StoryObj } from '@storybook/react-vite'
import { StorageUsage } from './StorageUsage'

const meta: Meta<typeof StorageUsage> = {
  title: 'Dashboard/StorageUsage',
  component: StorageUsage,
  args: { retentionDays: 30 },
}

export default meta
type Story = StoryObj<typeof StorageUsage>

export const Low: Story = { args: { usedBytes: 500_000_000, limitBytes: 5_000_000_000 } }
export const NearLimit: Story = { args: { usedBytes: 4_800_000_000, limitBytes: 5_000_000_000 } }
export const Loading: Story = { args: { usedBytes: 0, limitBytes: 0, isLoading: true } }
export const ErrorState: Story = { args: { usedBytes: 0, limitBytes: 0, isError: true } }
