import type { SelectHTMLAttributes } from 'react'
import styles from './Select.module.css'

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label: string
  options: SelectOption[]
  help?: string
}

export function Select({ label, options, help, id, ...rest }: SelectProps) {
  const selectId = id ?? `select-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <label className={styles.field} htmlFor={selectId}>
      {label}
      <select id={selectId} className={styles.select} {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {help && <small className={styles.help}>{help}</small>}
    </label>
  )
}
