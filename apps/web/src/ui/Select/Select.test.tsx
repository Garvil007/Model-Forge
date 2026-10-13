import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Select } from './Select'

const OPTIONS = [
  { value: 'vision', label: 'Vision / CNN' },
  { value: 'llm', label: 'Language model (LLM)' },
]

describe('Select', () => {
  it('renders its options and label', () => {
    render(<Select label="Model type" options={OPTIONS} defaultValue="vision" />)
    expect(screen.getByLabelText('Model type')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Language model (LLM)' })).toBeInTheDocument()
  })

  it('reports value changes', async () => {
    const onChange = vi.fn()
    render(
      <Select label="Model type" options={OPTIONS} defaultValue="vision" onChange={onChange} />,
    )
    await userEvent.selectOptions(screen.getByLabelText('Model type'), 'llm')
    expect(onChange).toHaveBeenCalled()
  })
})
