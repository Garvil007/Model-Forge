import type { ReactNode } from 'react'
import { Badge } from '../../ui/Badge/Badge'
import { cx } from '../../ui/cx'
import type { AvailabilityResult } from './availability'
import styles from './MethodList.module.css'
import type { Operation } from './types'

export interface MethodRowProps {
  operation: Operation
  availability: AvailabilityResult
  selected: boolean
  onSelect: () => void
  children?: ReactNode
}

/** One method/convert-target row: name, accuracy badge, description, and either the
 * typical-impact/time metadata (available) or the disabled reason (unavailable) — port of the
 * prototype's `.op` list item. */
export function MethodRow({
  operation,
  availability,
  selected,
  onSelect,
  children,
}: MethodRowProps) {
  const inputId = `op-${operation.id}`
  const disabled = !availability.ok

  return (
    <li
      className={cx(styles.op, selected && styles.selected, disabled && styles.off)}
      aria-disabled={disabled || undefined}
    >
      <input
        type="radio"
        name="op"
        id={inputId}
        checked={selected}
        disabled={disabled}
        onChange={onSelect}
        className={styles.radio}
      />
      <label htmlFor={inputId} className={styles.name}>
        {operation.label}
      </label>
      <Badge variant={operation.accuracy} className={styles.badge} />
      <div className={styles.desc}>{operation.description}</div>
      {disabled ? (
        <div className={styles.why}>{availability.why}</div>
      ) : (
        <div className={styles.meta}>
          <span>
            Typical impact: <b>{operation.typicalImpact}</b>
          </span>
          <span>
            Takes: <b>{operation.timeEstimate}</b>
          </span>
        </div>
      )}
      {selected && children && <div className={styles.rowDetails}>{children}</div>}
    </li>
  )
}
