import { describe, expect, it } from 'vitest'
import { estimateOutputBytes, summarizeSizeChange } from './sizeEstimateFormulas'
import type { ModelInfo } from './types'

const resnet: ModelInfo = {
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25.6e6,
  size: 102_442_450,
}
const llama: ModelInfo = {
  format: 'safetensors',
  family: 'llm',
  bits: 16,
  params: 1.236e9,
  size: 2_471_645_608,
}

describe('estimateOutputBytes', () => {
  it('halves size for FP16 from a 32-bit model', () => {
    expect(estimateOutputBytes('q_fp16', resnet, {})).toBe(Math.round((resnet.size * 16) / 32))
  })

  it('computes GGUF size from param count and quant type bits-per-weight', () => {
    const bytes = estimateOutputBytes('q_gguf', llama, { qtype: 'Q4_K_M' })
    expect(bytes).toBe(Math.round((llama.params * 4.8) / 8))
  })

  it('computes GPTQ size from bits and group size', () => {
    const bytes = estimateOutputBytes('q_gptq', llama, { bits: '4', group: '128' })
    expect(bytes).toBe(Math.round((llama.params * (4 + 32 / 128)) / 8))
  })

  it('returns null for distillation with a custom student (unknown size)', () => {
    expect(estimateOutputBytes('d_logit', resnet, { student: 'custom' })).toBeNull()
  })

  it('returns a concrete size for a known distillation student preset', () => {
    const bytes = estimateOutputBytes('d_logit', resnet, { student: 'half_width' })
    expect(bytes).toBe(Math.round(0.25 * resnet.size * (32 / resnet.bits)))
  })

  it('keeps magnitude pruning dense storage at the original size', () => {
    expect(estimateOutputBytes('p_magnitude', resnet, { storage: 'dense', sparsity: 50 })).toBe(
      resnet.size,
    )
  })

  it('shrinks sparse magnitude pruning output with sparsity', () => {
    const bytes = estimateOutputBytes('p_magnitude', resnet, { storage: 'sparse', sparsity: 50 })
    expect(bytes).toBe(Math.round(resnet.size * Math.min(1, 0.5 * 1.3)))
  })

  it('returns null for an unknown operation id', () => {
    expect(estimateOutputBytes('not_an_op', resnet, {})).toBeNull()
  })
})

describe('summarizeSizeChange', () => {
  it('reports smaller when the output shrinks', () => {
    expect(summarizeSizeChange(50, 100)).toEqual({ bytes: 50, percent: 50, direction: 'smaller' })
  })

  it('reports larger when the output grows', () => {
    expect(summarizeSizeChange(150, 100)).toEqual({ bytes: 150, percent: 50, direction: 'larger' })
  })

  it('reports same when the output is unchanged', () => {
    expect(summarizeSizeChange(100, 100)).toEqual({ bytes: 100, percent: 0, direction: 'same' })
  })
})
