import { useState, type InputHTMLAttributes } from 'react'
import styles from './Range.module.css'

export interface RangeProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
  unit?: string
  help?: string
}

export function Range({
  label,
  unit = '',
  help,
  id,
  defaultValue,
  value,
  onChange,
  ...rest
}: RangeProps) {
  const inputId = id ?? `range-${label.toLowerCase().replace(/\s+/g, '-')}`
  const [uncontrolled, setUncontrolled] = useState(defaultValue ?? rest.min ?? 0)
  const current = value ?? uncontrolled

  return (
    <label className={styles.field} htmlFor={inputId}>
      {label}
      <span className={styles.row}>
        <input
          id={inputId}
          type="range"
          className={styles.slider}
          value={value}
          defaultValue={value === undefined ? defaultValue : undefined}
          onChange={(event) => {
            setUncontrolled(event.target.value)
            onChange?.(event)
          }}
          {...rest}
        />
        <output className={styles.output} htmlFor={inputId}>
          {current}
          {unit}
        </output>
      </span>
      {help && <small className={styles.help}>{help}</small>}
    </label>
  )
}
