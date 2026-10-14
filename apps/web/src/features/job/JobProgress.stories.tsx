import type { Meta, StoryObj } from '@storybook/react-vite'
import type { JobStage } from '../../api/types'
import { JobProgress } from './JobProgress'

const meta: Meta<typeof JobProgress> = {
  title: 'Job/JobProgress',
  component: JobProgress,
  args: { elapsedSeconds: 12, reconnecting: false, onCancel: () => {} },
}

export default meta
type Story = StoryObj<typeof JobProgress>

const quantizationStages: JobStage[] = [
  { label: 'Loading model', status: 'done' },
  { label: 'Running calibration data', status: 'active' },
  { label: 'Quantizing weights', status: 'pending' },
  { label: 'Measuring accuracy', status: 'pending' },
]

export const EarlyStage: Story = { args: { stages: quantizationStages } }

export const TrainingMidRun40Epochs: Story = {
  args: {
    elapsedSeconds: 185,
    stages: [
      { label: 'Loading teacher', status: 'done' },
      { label: 'Building student', status: 'done' },
      { label: 'Training student', status: 'active', epoch: 17, totalEpochs: 40 },
      { label: 'Measuring accuracy', status: 'pending' },
    ],
  },
}

export const Reconnecting: Story = {
  args: { stages: quantizationStages, reconnecting: true },
}

export const LastStageDone: Story = {
  args: {
    elapsedSeconds: 42,
    stages: quantizationStages.map((s) => ({ ...s, status: 'done' })),
  },
}
