import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ThemeContext } from './ThemeContext'
import { readStoredTheme, writeStoredTheme, type ThemeChoice } from './theme-storage'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(() => readStoredTheme())

  useEffect(() => {
    const root = document.documentElement
    if (choice === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', choice)
  }, [choice])

  const setChoice = (next: ThemeChoice) => {
    writeStoredTheme(next)
    setChoiceState(next)
  }

  const value = useMemo(() => ({ choice, setChoice }), [choice])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
