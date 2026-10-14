import { useRef, type KeyboardEvent } from 'react'
import { cx } from '../../ui/cx'
import styles from './TechniqueTable.module.css'
import type { Technique } from './types'

export interface TechniqueTableProps {
  techniques: Technique[]
  value: string
  onChange: (id: string) => void
  'aria-label'?: string
}

/** The prototype's technique comparison table, doubling as a radio group — four columns
 * (technique, how it works, hardware impact, effort meter) collapsing to a stacked card below
 * 640px with "How:"/"Impact:" labels. Full keyboard support: arrow keys move focus, Space/Enter
 * selects (native `<button>` activation). */
export function TechniqueTable({
  techniques,
  value,
  onChange,
  'aria-label': ariaLabel = 'Compression technique',
}: TechniqueTableProps) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  const focusAndSelect = (id: string) => {
    onChange(id)
    refs.current[id]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = techniques.findIndex((t) => t.id === value)
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      focusAndSelect(techniques[(index + 1) % techniques.length].id)
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      focusAndSelect(techniques[(index - 1 + techniques.length) % techniques.length].id)
    } else if (event.key === 'Home') {
      focusAndSelect(techniques[0].id)
    } else if (event.key === 'End') {
      focusAndSelect(techniques[techniques.length - 1].id)
    } else {
      return
    }
    event.preventDefault()
  }

  return (
    <div className={styles.techs} role="radiogroup" aria-label={ariaLabel} onKeyDown={onKeyDown}>
      <div className={styles.head} aria-hidden="true">
        <span>Technique</span>
        <span>How it works</span>
        <span>Hardware impact</span>
        <span>Effort</span>
      </div>
      {techniques.map((technique) => {
        const checked = technique.id === value
        return (
          <button
            key={technique.id}
            ref={(el) => {
              refs.current[technique.id] = el
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            className={cx(styles.row, checked && styles.rowChecked)}
            onClick={() => onChange(technique.id)}
          >
            <span className={styles.name}>
              {technique.name}
              <small>{technique.tag}</small>
            </span>
            <span className={styles.cell}>
              <span className={styles.mobileLabel}>How: </span>
              {technique.mechanism}
            </span>
            <span className={styles.cell}>
              <span className={styles.mobileLabel}>Impact: </span>
              {technique.hardwareImpact}
            </span>
            <span className={cx(styles.cell, styles.effort)}>
              <span className={styles.bars} aria-hidden="true">
                {technique.bars.map((bar, i) => (
                  <i
                    key={i}
                    className={cx(bar === 1 && styles.barOn, bar > 0 && bar < 1 && styles.barHalf)}
                  />
                ))}
              </span>
              {technique.complexity}
            </span>
          </button>
        )
      })}
    </div>
  )
}
