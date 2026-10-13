import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Skeleton } from './Skeleton'

describe('Skeleton', () => {
  it('renders a hidden placeholder sized to its props', () => {
    const { container } = render(<Skeleton width="200px" height="20px" />)
    const el = container.firstChild as HTMLElement
    expect(el).toHaveAttribute('aria-hidden', 'true')
    expect(el.style.width).toBe('200px')
    expect(el.style.height).toBe('20px')
  })
})
