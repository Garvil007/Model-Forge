import type { InputHTMLAttributes } from 'react'
import styles from './Toggle.module.css'

export interface ToggleProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
}

export function Toggle({ label, id, ...rest }: ToggleProps) {
  const inputId = id ?? `toggle-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <label className={styles.label} htmlFor={inputId}>
      <input id={inputId} type="checkbox" role="switch" className={styles.checkbox} {...rest} />
      <span className={styles.track} aria-hidden="true" />
      {label}
    </label>
  )
}
