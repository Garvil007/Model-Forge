import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { Tabs } from './Tabs'

const meta: Meta<typeof Tabs> = {
  title: 'UI/Tabs',
  component: Tabs,
}

export default meta
type Story = StoryObj<typeof Tabs>

const TABS = [
  { id: 'compress', label: 'Compress' },
  { id: 'convert', label: 'Convert' },
]

export const Default: Story = {
  render: () => {
    function Demo() {
      const [active, setActive] = useState('compress')
      return <Tabs tabs={TABS} activeId={active} onChange={setActive} aria-label="What to do" />
    }
    return <Demo />
  },
}
