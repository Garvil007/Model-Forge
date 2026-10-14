import type { Meta, StoryObj } from '@storybook/react-vite'
import { ConfirmDialog } from './ConfirmDialog'

const meta: Meta<typeof ConfirmDialog> = {
  title: 'Job/ConfirmDialog',
  component: ConfirmDialog,
  args: { onConfirm: () => {}, onCancel: () => {} },
}

export default meta
type Story = StoryObj<typeof ConfirmDialog>

export const ExpensiveJob: Story = {
  args: {
    title: 'This job runs on a GPU / takes a while',
    body: 'Running "4-bit GPTQ" on your model will take some time and cost real money.',
    meta: ['Estimated time: 10 to 60 minutes on a GPU', 'Estimated cost: $0.90–$3.60'],
    confirmLabel: 'Start job',
  },
}

export const CancelJob: Story = {
  args: {
    title: 'Cancel this job?',
    body: 'Progress made so far will be discarded.',
    confirmLabel: 'Cancel job',
    cancelLabel: 'Keep running',
  },
}
