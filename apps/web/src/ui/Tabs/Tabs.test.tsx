import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { Tabs } from './Tabs'

const TABS = [
  { id: 'compress', label: 'Compress' },
  { id: 'convert', label: 'Convert' },
]

function Controlled() {
  const [active, setActive] = useState('compress')
  return <Tabs tabs={TABS} activeId={active} onChange={setActive} aria-label="What to do" />
}

describe('Tabs', () => {
  it('marks the active tab as selected', () => {
    render(<Controlled />)
    expect(screen.getByRole('tab', { name: 'Compress' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Convert' })).toHaveAttribute('aria-selected', 'false')
  })

  it('moves selection and focus with ArrowRight', async () => {
    render(<Controlled />)
    const user = userEvent.setup()
    screen.getByRole('tab', { name: 'Compress' }).focus()
    await user.keyboard('{ArrowRight}')
    const convert = screen.getByRole('tab', { name: 'Convert' })
    expect(convert).toHaveAttribute('aria-selected', 'true')
    expect(convert).toHaveFocus()
  })
})
