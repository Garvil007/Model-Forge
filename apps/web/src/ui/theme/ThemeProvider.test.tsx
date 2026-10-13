import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ThemeProvider } from './ThemeProvider'
import { useTheme } from './useTheme'

function Probe() {
  const { choice, setChoice } = useTheme()
  return (
    <div>
      <span data-testid="choice">{choice}</span>
      <button onClick={() => setChoice('dark')}>go dark</button>
    </div>
  )
}

afterEach(() => {
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeProvider', () => {
  it('defaults to system when nothing is stored', () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('choice')).toHaveTextContent('system')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('reads a previously stored choice on mount', () => {
    window.localStorage.setItem('modelforge.theme', 'dark')
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('choice')).toHaveTextContent('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})
