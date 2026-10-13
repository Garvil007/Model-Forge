import { createContext } from 'react'
import type { ThemeChoice } from './theme-storage'

export interface ThemeContextValue {
  choice: ThemeChoice
  setChoice: (choice: ThemeChoice) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)
