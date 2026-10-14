import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { ModelPanel } from './ModelPanel'

const meta: Meta<typeof ModelPanel> = {
  title: 'Model/ModelPanel',
  component: ModelPanel,
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <Story />
      </QueryClientProvider>
    ),
  ],
}
export default meta
type Story = StoryObj<typeof ModelPanel>

/** Empty state — pick a file, try a sample, or switch to the Hugging Face tab. */
export const Empty: Story = {}
