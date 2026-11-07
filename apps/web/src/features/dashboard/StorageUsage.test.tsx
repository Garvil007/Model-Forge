import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StorageUsage } from './StorageUsage'

describe('StorageUsage', () => {
  it('shows a loading skeleton while the query is pending', () => {
    render(<StorageUsage usedBytes={0} limitBytes={0} retentionDays={30} isLoading />)
    expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(1)
  })

  it('shows an error notice when the query fails', () => {
    render(<StorageUsage usedBytes={0} limitBytes={0} retentionDays={30} isError />)
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load/i)
  })

  it('shows used/limit and the retention note', () => {
    render(<StorageUsage usedBytes={500_000_000} limitBytes={5_000_000_000} retentionDays={30} />)
    expect(screen.getByText(/476\.8 MB of 4\.66 GB used/)).toBeInTheDocument()
    expect(screen.getByText(/kept for 30 days/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '10')
  })

  it('caps the progress bar at 100% when usage exceeds the limit', () => {
    render(<StorageUsage usedBytes={6_000_000_000} limitBytes={5_000_000_000} retentionDays={30} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })
})
