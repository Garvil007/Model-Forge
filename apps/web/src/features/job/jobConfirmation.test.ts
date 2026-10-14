import { describe, expect, it } from 'vitest'
import type { ModelInfo, Operation } from '../catalog/types'
import { estimateJobCost, isExpensiveOperation } from './jobConfirmation'

const baseOp: Operation = {
  id: 'q_fp16',
  technique: 'quantization',
  label: 'FP16 weights',
  description: '',
  accuracy: 'lossless',
  typicalImpact: '',
  timeEstimate: 'seconds',
  sourceFormats: ['onnx'],
  workerImage: 'cpu-base',
  queue: 'cpu',
}

const model: ModelInfo = {
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 1e6,
  size: 1_000_000_000,
}

describe('isExpensiveOperation', () => {
  it('is never expensive for a cheap CPU job', () => {
    expect(isExpensiveOperation(baseOp)).toBe(false)
  })

  it('is expensive when the operation queues on the GPU', () => {
    expect(isExpensiveOperation({ ...baseOp, queue: 'gpu' })).toBe(true)
  })

  it('is expensive when the time estimate mentions hours or days even on CPU', () => {
    expect(isExpensiveOperation({ ...baseOp, timeEstimate: 'hours with fine-tuning' })).toBe(true)
    expect(isExpensiveOperation({ ...baseOp, timeEstimate: 'days on multiple GPUs' })).toBe(true)
  })
})

describe('estimateJobCost', () => {
  it('returns the catalog time estimate verbatim and a non-empty cost range', () => {
    const op: Operation = { ...baseOp, queue: 'gpu', timeEstimate: '10 to 60 minutes on a GPU' }
    const estimate = estimateJobCost(op, model)
    expect(estimate.time).toBe('10 to 60 minutes on a GPU')
    expect(estimate.cost).toMatch(/^\$\d+\.\d{2}–\$\d+\.\d{2}$/)
  })
})
