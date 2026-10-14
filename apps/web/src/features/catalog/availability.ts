import { formatLabel } from './formatLabels'
import type { ModelInfo, Operation } from './types'

export interface AvailabilityResult {
  ok: boolean
  why?: string
}

/** Port of docs/ui-prototype.html's `availability()` — pure function, no DOM/state access. */
export function checkAvailability(
  op: Operation,
  model: ModelInfo | null | undefined,
): AvailabilityResult {
  if (!model) return { ok: false }

  if (model.format === 'gguf') {
    return { ok: false, why: 'Not available for GGUF files, which are already quantized.' }
  }

  if (!op.sourceFormats.includes(model.format)) {
    const list = op.sourceFormats.map(formatLabel).join(', ')
    return {
      ok: false,
      why: `Not available for ${formatLabel(model.format)}. Works with ${list}.`,
    }
  }

  if (op.allowedFamilies && !op.allowedFamilies.includes(model.family)) {
    const why = op.allowedFamilies.includes('llm')
      ? 'Only for language models. Change the model type if this is one.'
      : 'Not for language models; see LLM distillation.'
    return { ok: false, why }
  }

  if (op.requiredBitWidth !== undefined && model.bits < op.requiredBitWidth) {
    return { ok: false, why: `Your model is already ${model.bits}-bit.` }
  }

  if (op.targetFormat && op.targetFormat === model.format) {
    return { ok: false, why: 'Your model is already in this format.' }
  }

  return { ok: true }
}

export interface AvailabilityRow {
  operation: Operation
  availability: AvailabilityResult
}

/** Available operations first, stable order preserved within each group — matches the
 * prototype's `.sort((x, y) => y.a.ok - x.a.ok)`. */
export function sortByAvailability(
  operations: Operation[],
  model: ModelInfo | null | undefined,
): AvailabilityRow[] {
  return operations
    .map((operation) => ({ operation, availability: checkAvailability(operation, model) }))
    .sort((a, b) => Number(b.availability.ok) - Number(a.availability.ok))
}
