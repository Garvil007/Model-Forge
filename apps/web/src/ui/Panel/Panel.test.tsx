import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Panel } from './Panel'

describe('Panel', () => {
  it('renders its children', () => {
    render(<Panel aria-label="Your model">content</Panel>)
    expect(screen.getByLabelText('Your model')).toHaveTextContent('content')
  })
})
