import type { Meta, StoryObj } from '@storybook/react-vite'
import { ThemeProvider } from './ThemeProvider'
import { ThemeToggle } from './ThemeToggle'

const meta: Meta<typeof ThemeToggle> = {
  title: 'UI/ThemeToggle',
  component: ThemeToggle,
  decorators: [(Story) => <ThemeProvider>{Story()}</ThemeProvider>],
}

export default meta
type Story = StoryObj<typeof ThemeToggle>

export const Default: Story = {}
