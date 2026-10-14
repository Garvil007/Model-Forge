import type { Meta, StoryObj } from '@storybook/react-vite'
import { ToastViewport } from './Toast'

const meta: Meta<typeof ToastViewport> = {
  title: 'ui/Toast',
  component: ToastViewport,
}

export default meta
type Story = StoryObj<typeof ToastViewport>

export const AllVariants: Story = {
  args: {
    toasts: [
      { id: '1', message: 'Settings saved.', variant: 'success', duration: 0 },
      {
        id: '2',
        message: 'Heads up: this model family is experimental.',
        variant: 'info',
        duration: 0,
      },
      { id: '3', message: 'Your session will expire soon.', variant: 'warning', duration: 0 },
      { id: '4', message: 'Could not reach the server.', variant: 'error', duration: 0 },
    ],
    onDismiss: () => {},
  },
}
