export type ThemeChoice = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'modelforge.theme'

export function readStoredTheme(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // localStorage can throw in private browsing / disabled storage — fall back silently.
  }
  return 'system'
}

export function writeStoredTheme(choice: ThemeChoice): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, choice)
  } catch {
    // Persisting the choice is a nice-to-have; losing it shouldn't break the app.
  }
}
