import type { Meta, StoryObj } from '@storybook/react-vite'
import { Toggle } from './Toggle'

const meta: Meta<typeof Toggle> = {
  title: 'UI/Toggle',
  component: Toggle,
  args: { label: 'Fine-tune afterwards to recover accuracy' },
}

export default meta
type Story = StoryObj<typeof Toggle>

export const Off: Story = { args: { defaultChecked: false } }
export const On: Story = { args: { defaultChecked: true } }
