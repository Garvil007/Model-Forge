import { describe, expect, it } from 'vitest'
import { checkAvailability, sortByAvailability } from './availability'
import type { ModelInfo, Operation } from './types'
import { CATALOG } from './types'

/** Sample models ported from docs/ui-prototype.html's SAMPLES, plus a GGUF file to cover the
 * "already quantized, convert only" lock. */
const SAMPLE_MODELS: Record<string, ModelInfo> = {
  resnet: { format: 'onnx', family: 'vision', bits: 32, params: 25.6e6, size: 102_442_450 },
  llama: { format: 'safetensors', family: 'llm', bits: 16, params: 1.236e9, size: 2_471_645_608 },
  yolo: { format: 'yolo', family: 'vision', bits: 32, params: 3.2e6, size: 6_549_796 },
  mobilenet: { format: 'keras', family: 'vision', bits: 32, params: 3.5e6, size: 14_536_120 },
  quantized: { format: 'gguf', family: 'llm', bits: 4.8, params: 1e9, size: 500_000_000 },
}

/** Independent re-derivation of the prototype's rules, not a copy of checkAvailability's code,
 * so the table-driven assertions below are a real spec check rather than a tautology. */
function referenceOk(op: Operation, model: ModelInfo): boolean {
  if (model.format === 'gguf') return false
  if (!op.sourceFormats.includes(model.format)) return false
  if (
    op.allowedFamilies &&
    op.allowedFamilies.length > 0 &&
    !op.allowedFamilies.includes(model.family)
  ) {
    return false
  }
  if (typeof op.requiredBitWidth === 'number' && model.bits < op.requiredBitWidth) return false
  if (op.targetFormat && op.targetFormat === model.format) return false
  return true
}

describe('checkAvailability', () => {
  it('returns not-ok with no reason when there is no model', () => {
    const op = CATALOG.operations[0]
    expect(checkAvailability(op, null)).toEqual({ ok: false })
  })

  for (const op of CATALOG.operations) {
    for (const [sampleName, model] of Object.entries(SAMPLE_MODELS)) {
      it(`${op.id} vs ${sampleName} matches the reference rules`, () => {
        const result = checkAvailability(op, model)
        expect(result.ok).toBe(referenceOk(op, model))
        if (!result.ok) {
          expect(typeof result.why).toBe('string')
          expect(result.why!.length).toBeGreaterThan(0)
        } else {
          expect(result.why).toBeUndefined()
        }
      })
    }
  }

  it('locks every operation out for an already-quantized GGUF file', () => {
    for (const op of CATALOG.operations) {
      const result = checkAvailability(op, SAMPLE_MODELS.quantized)
      expect(result).toEqual({
        ok: false,
        why: 'Not available for GGUF files, which are already quantized.',
      })
    }
  })

  it('names the source format and supported formats when unavailable', () => {
    const q_bf16 = CATALOG.operations.find((op) => op.id === 'q_bf16')!
    expect(checkAvailability(q_bf16, SAMPLE_MODELS.resnet)).toEqual({
      ok: false,
      why: 'Not available for ONNX. Works with PyTorch, safetensors.',
    })
  })

  it('blocks family-restricted LLM methods for the right model, allows it for a matching one', () => {
    const q_gguf = CATALOG.operations.find((op) => op.id === 'q_gguf')!
    const visionTorch: ModelInfo = {
      format: 'torch',
      family: 'vision',
      bits: 32,
      params: 1e6,
      size: 1e6,
    }
    expect(checkAvailability(q_gguf, visionTorch)).toEqual({
      ok: false,
      why: 'Only for language models. Change the model type if this is one.',
    })
    expect(checkAvailability(q_gguf, SAMPLE_MODELS.llama).ok).toBe(true)
  })

  it('blocks vision-only distillation for an LLM model in a runnable format', () => {
    const d_logit = CATALOG.operations.find((op) => op.id === 'd_logit')!
    const llmTorch: ModelInfo = { format: 'torch', family: 'llm', bits: 16, params: 1e9, size: 1e9 }
    expect(checkAvailability(d_logit, llmTorch)).toEqual({
      ok: false,
      why: 'Not for language models; see LLM distillation.',
    })
  })

  it('blocks required-bit-width methods on already-narrow models', () => {
    const q_fp16 = CATALOG.operations.find((op) => op.id === 'q_fp16')!
    expect(checkAvailability(q_fp16, SAMPLE_MODELS.llama)).toEqual({
      ok: false,
      why: 'Your model is already 16-bit.',
    })
  })

  it('blocks converting to the format the model is already in', () => {
    const toOnnx: Operation = {
      id: 'c_test_onnx',
      technique: 'convert',
      label: 'ONNX',
      description: '',
      accuracy: 'lossless',
      typicalImpact: '',
      timeEstimate: '',
      sourceFormats: ['onnx', 'torch'],
      workerImage: 'cpu-base',
      queue: 'cpu',
      targetFormat: 'onnx',
    }
    expect(checkAvailability(toOnnx, SAMPLE_MODELS.resnet)).toEqual({
      ok: false,
      why: 'Your model is already in this format.',
    })
  })
})

describe('sortByAvailability', () => {
  it('sorts available operations above unavailable ones', () => {
    const rows = sortByAvailability(CATALOG.operations, SAMPLE_MODELS.resnet)
    const firstUnavailable = rows.findIndex((row) => !row.availability.ok)
    const lastAvailable = rows.map((row) => row.availability.ok).lastIndexOf(true)
    expect(firstUnavailable === -1 || lastAvailable < firstUnavailable).toBe(true)
  })
})
