import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Toggle } from './Toggle'

describe('Toggle', () => {
  it('toggles checked state on click', async () => {
    render(<Toggle label="Fine-tune afterwards to recover accuracy" defaultChecked={false} />)
    const switchEl = screen.getByRole('switch', {
      name: 'Fine-tune afterwards to recover accuracy',
    })
    expect(switchEl).not.toBeChecked()
    await userEvent.click(switchEl)
    expect(switchEl).toBeChecked()
  })
})
