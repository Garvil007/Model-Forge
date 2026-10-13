import type { ThemeChoice } from './theme-storage'
import { useTheme } from './useTheme'
import styles from './ThemeToggle.module.css'

const OPTIONS: Array<{ value: ThemeChoice; label: string }> = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
]

export function ThemeToggle() {
  const { choice, setChoice } = useTheme()

  return (
    <div className={styles.toggle} role="radiogroup" aria-label="Theme">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={choice === option.value}
          className={
            choice === option.value ? `${styles.option} ${styles.optionActive}` : styles.option
          }
          onClick={() => setChoice(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
