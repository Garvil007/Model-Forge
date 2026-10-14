import type { DetectedModel } from './types'

/** Mirrors `docs/ui-prototype.html`'s `EXT` map (lines 513-514). */
const EXTENSION_FORMAT: Record<string, string> = {
  onnx: 'onnx',
  tflite: 'tflite',
  keras: 'keras',
  h5: 'keras',
  hdf5: 'keras',
  safetensors: 'safetensors',
  pt: 'torch',
  pth: 'torch',
  bin: 'torch',
  ckpt: 'torch',
  gguf: 'gguf',
}

export const ACCEPTED_EXTENSIONS =
  '.onnx,.tflite,.h5,.hdf5,.keras,.pt,.pth,.bin,.ckpt,.safetensors,.gguf'

const LLM_NAME_PATTERN = /llama|mistral|qwen|gemma|phi|gpt|falcon|olmo|deepseek/i
const YOLO_NAME_PATTERN = /yolo/i

export class UnsupportedFormatError extends Error {}
export class OversizedFileError extends Error {}

/** No real-world model file is anywhere near this; it exists to reject obvious mistakes (e.g. a
 * dataset zip) before any request goes out, per "reject oversized or wrong-type files before any
 * request goes out". */
export const MAX_FILE_BYTES = 5 * 1024 ** 3

/** Client-side-only format detection — the API never opens a user's model file (see
 * `CLAUDE.md`'s "Never load a user's model file inside the API" rule); only workers do, and they
 * only run after a model has already been registered. Port of `fromFile()` (prototype lines
 * 515-524): extension picks the format, filename heuristics pick family/YOLO, bit-width is a
 * guess used only for the size estimate until something more precise is known. */
export function detectModel(file: { name: string; size: number }): DetectedModel {
  if (file.size > MAX_FILE_BYTES) {
    throw new OversizedFileError(
      `That file is too large to upload (max 5 GB). If this is a real model, contact support.`,
    )
  }

  const ext = file.name.toLowerCase().split('.').pop() ?? ''
  const format = EXTENSION_FORMAT[ext]
  if (!format) {
    throw new UnsupportedFormatError(
      `Files ending in .${ext} aren't supported. Upload ONNX, TFLite, Keras (.keras, .h5), ` +
        'PyTorch (.pt, .pth), safetensors or GGUF.',
    )
  }

  const llmish = LLM_NAME_PATTERN.test(file.name) || format === 'safetensors' || format === 'gguf'
  const isYolo = YOLO_NAME_PATTERN.test(file.name) && format === 'torch'
  const bits = format === 'gguf' ? 4.8 : llmish ? 16 : 32

  return {
    filename: file.name,
    format: isYolo ? 'yolo' : format,
    family: llmish ? 'llm' : 'vision',
    bits,
    params: (file.size * 8) / bits,
    size: file.size,
    inputs: null,
    metric: null,
  }
}
