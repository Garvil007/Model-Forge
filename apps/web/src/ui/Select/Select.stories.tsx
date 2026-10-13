import type { Meta, StoryObj } from '@storybook/react-vite'
import { Select } from './Select'

const meta: Meta<typeof Select> = {
  title: 'UI/Select',
  component: Select,
  args: {
    label: 'Model type',
    options: [
      { value: 'vision', label: 'Vision / CNN' },
      { value: 'llm', label: 'Language model (LLM)' },
      { value: 'other', label: 'Other' },
    ],
    defaultValue: 'vision',
  },
}

export default meta
type Story = StoryObj<typeof Select>

export const Default: Story = {}
export const WithHelp: Story = { args: { help: 'Guessed from the file.' } }
