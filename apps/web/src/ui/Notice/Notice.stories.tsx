import type { Meta, StoryObj } from '@storybook/react-vite'
import { Notice } from './Notice'

const meta: Meta<typeof Notice> = {
  title: 'UI/Notice',
  component: Notice,
}

export default meta
type Story = StoryObj<typeof Notice>

export const Info: Story = { args: { variant: 'info', children: 'No files leave your browser.' } }
export const Warning: Story = {
  args: { variant: 'warning', children: 'GGUF files are already quantized.' },
}
export const Error: Story = {
  args: { variant: 'error', children: "Files ending in .foo aren't supported." },
}
