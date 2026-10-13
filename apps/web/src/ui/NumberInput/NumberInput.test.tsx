import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { NumberInput } from './NumberInput'

describe('NumberInput', () => {
  it('constrains to min/max and accepts typed values', async () => {
    render(<NumberInput label="Fine-tuning epochs" defaultValue={3} min={1} max={100} />)
    const input = screen.getByLabelText('Fine-tuning epochs')
    expect(input).toHaveAttribute('min', '1')
    expect(input).toHaveAttribute('max', '100')
    await userEvent.clear(input)
    await userEvent.type(input, '10')
    expect(input).toHaveValue(10)
  })
})
