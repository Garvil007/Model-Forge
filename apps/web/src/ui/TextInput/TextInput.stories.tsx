import type { Meta, StoryObj } from '@storybook/react-vite'
import { TextInput } from './TextInput'

const meta: Meta<typeof TextInput> = {
  title: 'UI/TextInput',
  component: TextInput,
  args: { label: 'Example input shape', defaultValue: '1,3,224,224' },
}

export default meta
type Story = StoryObj<typeof TextInput>

export const Default: Story = {}
export const WithHelp: Story = { args: { help: 'Comma-separated, including batch.' } }
export const Disabled: Story = { args: { disabled: true } }
