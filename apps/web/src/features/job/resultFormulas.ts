import type { ApiModel } from '../../api/types'
import { formatBytes, summarizeSizeChange } from '../catalog/sizeEstimateFormulas'
import type { Operation, ParamValues } from '../catalog/types'

export { formatBytes }

export interface SizeRuler {
  headline: string
  beforeBytes: number
  afterBytes: number
  beforeWidthPercent: number
  afterWidthPercent: number
}

/** Headline percentage + before/after ruler widths — port of `showResult()`'s first few lines. */
export function buildSizeRuler(model: ApiModel, outputBytes: number): SizeRuler {
  const { percent, direction } = summarizeSizeChange(outputBytes, model.size)
  const headline =
    direction === 'smaller'
      ? `${percent}% smaller`
      : direction === 'larger'
        ? `${percent}% larger`
        : 'Same size'
  const larger = Math.max(model.size, outputBytes)
  const beforeWidthPercent = Math.round((model.size / larger) * 100)
  const afterWidthPercent = Math.max(1, Math.round((outputBytes / larger) * 100))
  return {
    headline,
    beforeBytes: model.size,
    afterBytes: outputBytes,
    beforeWidthPercent,
    afterWidthPercent,
  }
}

/** Per-operation speed note shown next to the headline — port of `showResult()`'s `speed` map. */
const SPEED_NOTES: Record<string, (values: ParamValues) => string> = {
  q_int8_static: () => 'about 2 to 3 times faster on CPU',
  q_int8_dyn: () => 'about 1.5 to 2 times faster on CPU',
  p_structured: (v) => {
    const ratio = Number(v.ratio) || 30
    const factor = 1 / Math.pow(1 - ratio / 100, 1.6)
    return `about ${factor.toFixed(1)} times faster`
  },
  p_24: () => 'about 1.4 times faster on Ampere+ GPUs',
  l_tucker: () => 'about 1.5 to 2 times faster on CPU',
  q_gguf: () => 'runs on CPU with llama.cpp',
  c_tensorrt: () => 'about 2 to 4 times faster on the target GPU',
}

export function speedNoteFor(operation: Operation, values: ParamValues): string | null {
  return SPEED_NOTES[operation.id]?.(values) ?? null
}

const CONVERT_EXTENSIONS: Record<string, string> = {
  onnx: '.onnx',
  tflite: '.tflite',
  torchscript: '.pt',
  savedmodel: '.zip',
  safetensors: '.safetensors',
  gguf: '.gguf',
  openvino: '.zip',
  tensorrt: '.engine',
  coreml: '.mlpackage.zip',
}

const SOURCE_FORMAT_EXTENSIONS: Record<string, string> = {
  onnx: '.onnx',
  keras: '.keras',
  yolo: '.pt',
  torch: '.pt',
  torchscript: '.pt',
  safetensors: '.safetensors',
}

/** Download filename stem + extension — port of `showResult()`'s `ext`/`stem`/`tag` lines. */
export function downloadFilename(
  model: ApiModel,
  operation: Operation,
  values: ParamValues,
  isConvert: boolean,
): string {
  const stem = model.filename.split('/').pop()!.split('.')[0]
  const extension = isConvert
    ? CONVERT_EXTENSIONS[operation.targetFormat ?? '']
    : operation.id === 'q_gguf'
      ? '.gguf'
      : SOURCE_FORMAT_EXTENSIONS[model.format]
  const tag =
    operation.id === 'q_gguf' ? String(values.qtype) : operation.id.split('_').slice(1).join('-')
  return `${stem}_${tag}${extension ?? '.bin'}`
}
