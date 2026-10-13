import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Tooltip } from './Tooltip'

describe('Tooltip', () => {
  it('shows the label on focus and hides it on blur', async () => {
    render(
      <Tooltip label="Higher values soften the teacher's outputs.">
        <button>Temperature</button>
      </Tooltip>,
    )
    const user = userEvent.setup()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    await user.tab()
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      "Higher values soften the teacher's outputs.",
    )
    await user.tab()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})
