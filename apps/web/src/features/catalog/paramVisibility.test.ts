import { describe, expect, it } from 'vitest'
import { isParamShown, missingRequiredLabels, visibleParams } from './paramVisibility'
import type { Param } from './types'

describe('isParamShown', () => {
  it('is shown with no showIf/onlyFor', () => {
    const p: Param = { name: 'a', label: 'A', type: 'check' }
    expect(isParamShown(p, {}, 'onnx')).toBe(true)
  })

  it('respects showIf against sibling values', () => {
    const p: Param = {
      name: 'imatrix_text',
      label: 'Text',
      type: 'file',
      showIf: { field: 'imatrix', equals: true },
    }
    expect(isParamShown(p, { imatrix: true }, 'onnx')).toBe(true)
    expect(isParamShown(p, { imatrix: false }, 'onnx')).toBe(false)
    expect(isParamShown(p, {}, 'onnx')).toBe(false)
  })

  it('respects showIf with a non-boolean target value', () => {
    const p: Param = {
      name: 'calib',
      label: 'Calib',
      type: 'file',
      showIf: { field: 'dataset', equals: 'custom' },
    }
    expect(isParamShown(p, { dataset: 'custom' }, 'onnx')).toBe(true)
    expect(isParamShown(p, { dataset: 'wikitext2' }, 'onnx')).toBe(false)
  })

  it('respects onlyFor against the model format', () => {
    const p: Param = {
      name: 'shape',
      label: 'Shape',
      type: 'text',
      onlyFor: ['torch', 'torchscript'],
    }
    expect(isParamShown(p, {}, 'torch')).toBe(true)
    expect(isParamShown(p, {}, 'onnx')).toBe(false)
  })
})

describe('visibleParams / missingRequiredLabels', () => {
  const params: Param[] = [
    { name: 'calib', label: 'Calibration inputs', type: 'file', required: true },
    { name: 'samples', label: 'Samples', type: 'range', default: 300 },
    { name: 'extra', label: 'Extra', type: 'text', showIf: { field: 'calib', equals: 'set' } },
  ]

  it('filters to currently-visible params', () => {
    expect(visibleParams(params, {}, 'onnx').map((p) => p.name)).toEqual(['calib', 'samples'])
  })

  it('lists labels of required, visible, unfilled params', () => {
    expect(missingRequiredLabels(params, {}, 'onnx')).toEqual(['Calibration inputs'])
    expect(missingRequiredLabels(params, { calib: 'file.zip' }, 'onnx')).toEqual([])
  })
})
