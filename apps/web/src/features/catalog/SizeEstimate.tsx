import { estimateOutputBytes, formatBytes, summarizeSizeChange } from './sizeEstimateFormulas'
import styles from './SizeEstimate.module.css'
import { useDebouncedValue } from './useDebouncedValue'
import type { ModelInfo, ParamValues } from './types'

export interface SizeEstimateProps {
  operationId: string
  model: ModelInfo
  values: ParamValues
}

type Direction = ReturnType<typeof summarizeSizeChange>['direction']

const CHANGE_LABEL: Record<Direction, (p: number) => string> = {
  smaller: (p) => `${p}% smaller`,
  larger: (p) => `${p}% larger`,
  same: () => 'about the same size',
}

/** Live estimated output size + percentage change — port of the prototype's `estimateHTML()`.
 * Slider input is debounced so dragging a range param doesn't recompute on every tick. */
export function SizeEstimate({ operationId, model, values }: SizeEstimateProps) {
  const debouncedValues = useDebouncedValue(values)
  const bytes = estimateOutputBytes(operationId, model, debouncedValues)

  if (bytes == null) {
    return <div className={styles.estimate}>Estimated output: depends on your student model.</div>
  }

  const { percent, direction } = summarizeSizeChange(bytes, model.size)
  return (
    <div className={styles.estimate}>
      Estimated output: <b>{formatBytes(bytes)}</b>, {CHANGE_LABEL[direction](percent)}
    </div>
  )
}
