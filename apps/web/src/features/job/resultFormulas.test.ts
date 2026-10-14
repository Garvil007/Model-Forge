import { describe, expect, it } from 'vitest'
import type { ApiModel } from '../../api/types'
import type { Operation } from '../catalog/types'
import { buildSizeRuler, downloadFilename, speedNoteFor } from './resultFormulas'

const model: ApiModel = {
  id: 'model_1',
  filename: 'resnet50.onnx',
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25.6e6,
  size: 100_000_000,
  inputs: null,
  metric: null,
  validationFilename: null,
  source: 'upload',
  repoId: null,
  createdAt: '2026-01-01T00:00:00.000Z',
}

const op: Operation = {
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

describe('buildSizeRuler', () => {
  it('reports a smaller headline and before/after bytes', () => {
    const ruler = buildSizeRuler(model, 40_000_000)
    expect(ruler.headline).toBe('60% smaller')
    expect(ruler.beforeBytes).toBe(100_000_000)
    expect(ruler.afterBytes).toBe(40_000_000)
    expect(ruler.beforeWidthPercent).toBe(100)
  })

  it('reports "Same size" when output equals input', () => {
    expect(buildSizeRuler(model, 100_000_000).headline).toBe('Same size')
  })
})

describe('speedNoteFor', () => {
  it('returns a known note for an operation in the table', () => {
    expect(speedNoteFor({ ...op, id: 'q_int8_static' }, {})).toBe(
      'about 2 to 3 times faster on CPU',
    )
  })

  it('returns null for an operation with no speed note', () => {
    expect(speedNoteFor(op, {})).toBeNull()
  })
})

describe('downloadFilename', () => {
  it('builds "<stem>_<tag><ext>" for a compress operation', () => {
    expect(downloadFilename(model, op, {}, false)).toBe('resnet50_fp16.onnx')
  })

  it('uses the target format extension for a convert operation', () => {
    const convertOp: Operation = { ...op, id: 'c_tflite', targetFormat: 'tflite' }
    expect(downloadFilename(model, convertOp, {}, true)).toBe('resnet50_tflite.tflite')
  })
})
