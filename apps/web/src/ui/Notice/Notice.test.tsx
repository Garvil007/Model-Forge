import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Notice } from './Notice'

describe('Notice', () => {
  it('uses the alert role for the error variant', () => {
    render(<Notice variant="error">Files ending in .foo are not supported.</Notice>)
    expect(screen.getByRole('alert')).toHaveTextContent('Files ending in .foo are not supported.')
  })

  it('uses a status role for info and warning variants', () => {
    render(<Notice variant="warning">GGUF files are already quantized.</Notice>)
    expect(screen.getByRole('status')).toHaveTextContent('GGUF files are already quantized.')
  })
})
