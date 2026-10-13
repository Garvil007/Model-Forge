import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { TextInput } from './TextInput'

describe('TextInput', () => {
  it('accepts typed input', async () => {
    render(<TextInput label="Example input shape" defaultValue="" />)
    const input = screen.getByLabelText('Example input shape')
    await userEvent.type(input, '1,3,224,224')
    expect(input).toHaveValue('1,3,224,224')
  })

  it('shows help text', () => {
    render(<TextInput label="Example input shape" help="Comma-separated, including batch." />)
    expect(screen.getByText('Comma-separated, including batch.')).toBeInTheDocument()
  })
})
