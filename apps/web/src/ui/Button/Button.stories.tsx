import type { Meta, StoryObj } from '@storybook/react-vite'
import { Button } from './Button'

const meta: Meta<typeof Button> = {
  title: 'UI/Button',
  component: Button,
  args: { children: 'Compress model' },
}

export default meta
type Story = StoryObj<typeof Button>

export const Primary: Story = { args: { variant: 'primary' } }
export const Secondary: Story = { args: { variant: 'secondary' } }
export const LinkVariant: Story = { args: { variant: 'link', children: 'Try other settings' } }
export const Disabled: Story = { args: { variant: 'primary', disabled: true } }
export const Loading: Story = { args: { variant: 'primary', loading: true } }
