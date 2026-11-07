import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { JobHistoryFilters } from './JobHistoryFilters'

describe('JobHistoryFilters', () => {
  it('reports a status change without touching the other filters', async () => {
    const onChange = vi.fn()
    render(<JobHistoryFilters value={{ operationId: 'q_int8_static' }} onChange={onChange} />)
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'succeeded')
    expect(onChange).toHaveBeenCalledWith({ operationId: 'q_int8_static', status: 'succeeded' })
  })

  it('reports date range changes', async () => {
    const onChange = vi.fn()
    render(<JobHistoryFilters value={{}} onChange={onChange} />)
    await userEvent.type(screen.getByLabelText('From'), '2026-01-01')
    expect(onChange).toHaveBeenLastCalledWith({ dateFrom: '2026-01-01' })
  })
})
