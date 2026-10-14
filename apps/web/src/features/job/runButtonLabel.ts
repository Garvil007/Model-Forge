import { missingRequiredLabels } from '../catalog/paramVisibility'
import type { ModelInfo, Operation, ParamValues } from '../catalog/types'

export type JobTab = 'compress' | 'convert'

export interface RunButtonState {
  label: string
  disabled: boolean
}

/** Port of `docs/ui-prototype.html`'s `updateRun()` — the run button's label changes with
 * context (a missing required param wins over everything else) and it's disabled while a job
 * is already running or no operation is selected. */
export function runButtonState(
  tab: JobTab,
  operation: Operation | null | undefined,
  model: ModelInfo | null | undefined,
  values: ParamValues,
  running: boolean,
): RunButtonState {
  const verb = tab === 'compress' ? 'Compress' : 'Convert'
  if (!operation) {
    return { label: `${verb} model`, disabled: true }
  }

  const missing = missingRequiredLabels(operation.params, values, model?.format ?? '')
  if (missing.length > 0) {
    return { label: `Add ${missing[0].toLowerCase()} to continue`, disabled: true }
  }

  const action =
    tab === 'convert'
      ? `Convert to ${operation.label}`
      : operation.technique === 'distillation'
        ? 'Train the student model'
        : `${verb} with ${operation.label}`

  return { label: action, disabled: running }
}
