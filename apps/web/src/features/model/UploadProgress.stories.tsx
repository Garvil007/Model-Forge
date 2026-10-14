import type { Meta, StoryObj } from '@storybook/react-vite'
import { UploadProgress } from './UploadProgress'
import type { UploadProgressState } from './types'

const meta: Meta<typeof UploadProgress> = {
  title: 'Model/UploadProgress',
  component: UploadProgress,
}
export default meta
type Story = StoryObj<typeof UploadProgress>

const noop = () => {}

const UPLOADING: UploadProgressState = {
  status: 'uploading',
  bytesUploaded: 420_000_000,
  totalBytes: 1_000_000_000,
  bytesPerSecond: 12_500_000,
  secondsRemaining: 46,
  error: null,
}

export const Uploading: Story = {
  args: { state: UPLOADING, onPause: noop, onResume: noop, onCancel: noop },
}

export const Paused: Story = {
  args: {
    state: { ...UPLOADING, status: 'paused' },
    onPause: noop,
    onResume: noop,
    onCancel: noop,
  },
}

export const Completing: Story = {
  args: {
    state: { ...UPLOADING, status: 'completing', bytesUploaded: UPLOADING.totalBytes },
    onPause: noop,
    onResume: noop,
    onCancel: noop,
  },
}
