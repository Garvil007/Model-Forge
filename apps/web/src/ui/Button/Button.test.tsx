import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'

describe('Button', () => {
  it('renders its label', () => {
    render(<Button>Compress model</Button>)
    expect(screen.getByRole('button', { name: 'Compress model' })).toBeInTheDocument()
  })

  it('calls onClick when clicked', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Run</Button>)
    await userEvent.click(screen.getByRole('button', { name: 'Run' }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('is disabled while loading and shows a spinner', () => {
    render(<Button loading>Run</Button>)
    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})
