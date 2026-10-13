import { useId, useState, type ReactNode } from 'react'
import styles from './Tooltip.module.css'

export interface TooltipProps {
  label: string
  children: ReactNode
}

export function Tooltip({ label, children }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()

  return (
    <span
      className={styles.wrapper}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined}>{children}</span>
      {open && (
        <span role="tooltip" id={id} className={styles.bubble}>
          {label}
        </span>
      )}
    </span>
  )
}
