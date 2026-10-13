import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Chip } from './Chip'

describe('Chip', () => {
  it('renders as a button and responds to clicks', async () => {
    const onClick = vi.fn()
    render(<Chip onClick={onClick}>ResNet-50 (ONNX)</Chip>)
    await userEvent.click(screen.getByRole('button', { name: 'ResNet-50 (ONNX)' }))
    expect(onClick).toHaveBeenCalledOnce()
  })
})
