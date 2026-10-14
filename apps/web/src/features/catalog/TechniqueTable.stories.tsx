import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { TechniqueTable } from './TechniqueTable'
import { getTechniques } from './types'

const meta: Meta<typeof TechniqueTable> = {
  title: 'Catalog/TechniqueTable',
  component: TechniqueTable,
}

export default meta
type Story = StoryObj<typeof TechniqueTable>

const TECHNIQUES = getTechniques()

export const Default: Story = {
  render: () => {
    function Demo() {
      const [value, setValue] = useState(TECHNIQUES[0].id)
      return <TechniqueTable techniques={TECHNIQUES} value={value} onChange={setValue} />
    }
    return <Demo />
  },
}

export const Empty: Story = {
  render: () => <TechniqueTable techniques={[]} value="" onChange={() => {}} />,
}
