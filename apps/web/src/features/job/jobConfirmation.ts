import type { ModelInfo, Operation } from '../catalog/types'

/** Durations in `operation.timeEstimate` that count as "long-running" even on CPU — anything
 * mentioning hours or days, which is how the catalog phrases its slowest operations (see
 * docs/ui-prototype.html's time strings, e.g. "hours with fine-tuning", "days on multiple GPUs"). */
const LONG_RUNNING_PATTERN = /\bhour|\bday/i

export function isExpensiveOperation(operation: Operation): boolean {
  return operation.queue === 'gpu' || LONG_RUNNING_PATTERN.test(operation.timeEstimate)
}

export interface CostEstimate {
  time: string
  cost: string
}

/** Rough dollar estimate for the confirmation dialog — GPU jobs are billed per GPU-minute,
 * CPU jobs that are merely long-running are billed per vCPU-minute. Not meant to be exact, only
 * to give the user a sense of scale before they commit. */
export function estimateJobCost(operation: Operation, model: ModelInfo): CostEstimate {
  const ratePerMinute = operation.queue === 'gpu' ? 0.9 : 0.06
  const sizeFactor = Math.max(1, model.size / 1_000_000_000)
  const minutesLow = Math.max(1, Math.round(sizeFactor * 1))
  const minutesHigh = Math.max(minutesLow + 1, Math.round(sizeFactor * 4))
  const costLow = (minutesLow * ratePerMinute).toFixed(2)
  const costHigh = (minutesHigh * ratePerMinute).toFixed(2)
  return { time: operation.timeEstimate, cost: `$${costLow}–$${costHigh}` }
}
