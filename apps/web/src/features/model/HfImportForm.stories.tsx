import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { HfImportForm } from './HfImportForm'

const meta: Meta<typeof HfImportForm> = {
  title: 'Model/HfImportForm',
  component: HfImportForm,
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <Story />
      </QueryClientProvider>
    ),
  ],
}
export default meta
type Story = StoryObj<typeof HfImportForm>

export const Default: Story = {
  args: { onImported: () => {} },
}
