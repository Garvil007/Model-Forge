import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DropZone, FileInput } from './FileInput'

describe('DropZone', () => {
  it('shows the drop title and hint text', () => {
    render(<DropZone title="Drop a model file here" hint="or click to choose one" />)
    expect(screen.getByText('Drop a model file here')).toBeInTheDocument()
    expect(screen.getByText('or click to choose one')).toBeInTheDocument()
  })
})

describe('FileInput', () => {
  it('marks required fields in the label', () => {
    render(<FileInput label="Calibration inputs" required help="100 to 1,000 real inputs." />)
    expect(screen.getByText(/Calibration inputs \(required\)/)).toBeInTheDocument()
  })
})
