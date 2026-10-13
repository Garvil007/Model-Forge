import type { InputHTMLAttributes } from 'react'
import styles from './TextInput.module.css'

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  help?: string
}

export function TextInput({ label, help, id, ...rest }: TextInputProps) {
  const inputId = id ?? `text-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <label className={styles.field} htmlFor={inputId}>
      {label}
      <input id={inputId} type="text" className={styles.input} {...rest} />
      {help && <small className={styles.help}>{help}</small>}
    </label>
  )
}
