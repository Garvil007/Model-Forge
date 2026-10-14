import { describe, expect, it } from 'vitest'
import {
  detectModel,
  MAX_FILE_BYTES,
  OversizedFileError,
  UnsupportedFormatError,
} from './detectFormat'

describe('detectModel', () => {
  it('detects ONNX as a 32-bit vision model', () => {
    const model = detectModel({ name: 'resnet50.onnx', size: 1024 })
    expect(model).toMatchObject({ format: 'onnx', family: 'vision', bits: 32 })
  })

  it('detects safetensors as a 16-bit LLM', () => {
    const model = detectModel({ name: 'model.safetensors', size: 1024 })
    expect(model).toMatchObject({ format: 'safetensors', family: 'llm', bits: 16 })
  })

  it('detects GGUF as already-quantized at 4.8 bits', () => {
    const model = detectModel({ name: 'llama.gguf', size: 1024 })
    expect(model).toMatchObject({ format: 'gguf', family: 'llm', bits: 4.8 })
  })

  it('detects a .pt file named with "yolo" as the yolo format', () => {
    const model = detectModel({ name: 'yolov8n.pt', size: 1024 })
    expect(model.format).toBe('yolo')
    expect(model.family).toBe('vision')
  })

  it('detects an LLM-ish filename on a torch file as an LLM even without "yolo"', () => {
    const model = detectModel({ name: 'llama-7b.pt', size: 1024 })
    expect(model.family).toBe('llm')
  })

  it('estimates params from size and bit width', () => {
    const model = detectModel({ name: 'resnet50.onnx', size: 1_000_000 })
    expect(model.params).toBeCloseTo((1_000_000 * 8) / 32)
  })

  it('throws UnsupportedFormatError for an unrecognized extension', () => {
    expect(() => detectModel({ name: 'weights.xyz', size: 10 })).toThrow(UnsupportedFormatError)
  })

  it('includes the rejected extension in the error message', () => {
    expect(() => detectModel({ name: 'weights.xyz', size: 10 })).toThrow(/\.xyz/)
  })

  it('throws OversizedFileError for a file over the max size', () => {
    expect(() => detectModel({ name: 'huge.onnx', size: MAX_FILE_BYTES + 1 })).toThrow(
      OversizedFileError,
    )
  })
})
