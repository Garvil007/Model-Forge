import { describe, expect, it } from 'vitest'
import type { ModelInfo, Operation } from '../catalog/types'
import { runButtonState } from './runButtonLabel'

const model: ModelInfo = { format: 'onnx', family: 'vision', bits: 32, params: 1e6, size: 1000 }

const quantOp: Operation = {
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

const distillOp: Operation = {
  ...quantOp,
  id: 'd_logit',
  technique: 'distillation',
  label: 'Logit distillation',
}
const convertOp: Operation = { ...quantOp, id: 'c_onnx', technique: 'convert', label: 'ONNX' }

describe('runButtonState', () => {
  it('shows "<verb> model" and is disabled with no operation selected', () => {
    expect(runButtonState('compress', null, model, {}, false)).toEqual({
      label: 'Compress model',
      disabled: true,
    })
  })

  it('shows "Compress with <label>" for a compress operation', () => {
    expect(runButtonState('compress', quantOp, model, {}, false)).toEqual({
      label: 'Compress with FP16 weights',
      disabled: false,
    })
  })

  it('shows "Convert to <label>" on the convert tab', () => {
    expect(runButtonState('convert', convertOp, model, {}, false)).toEqual({
      label: 'Convert to ONNX',
      disabled: false,
    })
  })

  it('shows "Train the student model" for distillation', () => {
    expect(runButtonState('compress', distillOp, model, {}, false)).toEqual({
      label: 'Train the student model',
      disabled: false,
    })
  })

  it('prompts for a missing required param and stays disabled', () => {
    const opWithRequiredParam: Operation = {
      ...quantOp,
      params: [{ name: 'calib', label: 'Calibration inputs', type: 'file', required: true }],
    }
    expect(runButtonState('compress', opWithRequiredParam, model, {}, false)).toEqual({
      label: 'Add calibration inputs to continue',
      disabled: true,
    })
  })

  it('disables the button while a job is running', () => {
    expect(runButtonState('compress', quantOp, model, {}, true)).toEqual({
      label: 'Compress with FP16 weights',
      disabled: true,
    })
  })
})
