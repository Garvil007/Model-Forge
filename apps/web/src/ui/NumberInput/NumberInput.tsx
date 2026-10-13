import type { InputHTMLAttributes } from 'react'
import styles from './NumberInput.module.css'

export interface NumberInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
  help?: string
}

export function NumberInput({ label, help, id, ...rest }: NumberInputProps) {
  const inputId = id ?? `number-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <label className={styles.field} htmlFor={inputId}>
      {label}
      <input id={inputId} type="number" className={styles.input} {...rest} />
      {help && <small className={styles.help}>{help}</small>}
    </label>
  )
}
