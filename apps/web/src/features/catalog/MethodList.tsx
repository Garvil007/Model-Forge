import type { ReactNode } from 'react'
import { sortByAvailability } from './availability'
import styles from './MethodList.module.css'
import { MethodRow } from './MethodRow'
import type { ModelInfo, Operation } from './types'

export interface MethodListProps {
  operations: Operation[]
  model: ModelInfo | null | undefined
  selectedId: string | null
  onSelect: (id: string) => void
  /** Rendered inside the selected row — typically `MethodParams` + `SizeEstimate`. */
  renderSelected?: (operation: Operation) => ReactNode
  emptyMessage?: string
}

/** The method/convert-target list: sorts available operations above unavailable ones (stable
 * within each group) and renders one `MethodRow` per operation — port of the prototype's
 * `renderOps()`. */
export function MethodList({
  operations,
  model,
  selectedId,
  onSelect,
  renderSelected,
  emptyMessage = 'Upload a model or pick a sample to see which methods apply.',
}: MethodListProps) {
  if (!model) {
    return <p className={styles.empty}>{emptyMessage}</p>
  }

  const rows = sortByAvailability(operations, model)
  if (rows.length === 0) {
    return <p className={styles.empty}>No methods for this technique.</p>
  }

  return (
    <ul className={styles.ops}>
      {rows.map(({ operation, availability }) => {
        const selected = operation.id === selectedId
        return (
          <MethodRow
            key={operation.id}
            operation={operation}
            availability={availability}
            selected={selected}
            onSelect={() => availability.ok && onSelect(operation.id)}
          >
            {selected ? renderSelected?.(operation) : null}
          </MethodRow>
        )
      })}
    </ul>
  )
}
