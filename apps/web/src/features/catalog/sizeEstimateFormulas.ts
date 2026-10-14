import type { ModelInfo, ParamValues } from './types'

/** bits-per-weight per GGUF quantization type — mirrors
 * packages/catalog/src/modelforge_catalog/formats.py's GGUF_TYPES. */
const GGUF_BITS_PER_WEIGHT: Record<string, number> = {
  Q8_0: 8.5,
  Q6_K: 6.6,
  Q5_K_M: 5.7,
  Q4_K_M: 4.8,
  Q3_K_M: 3.9,
  Q2_K: 3.4,
}

const SHARE_OF_LINEAR: Record<string, number> = { llm: 0.9, vision: 0.15, other: 0.6 }

function svdRankShare(v: ParamValues): number {
  if (v.mode === 'energy') {
    return 0.1 + ((Number(v.energy) - 80) / 19) * 0.4
  }
  return Number(v.rank) / 100
}

type Estimator = (model: ModelInfo, values: ParamValues) => number | null

/** One estimator per operation id — direct TS port of the size/ratio closures in
 * docs/ui-prototype.html's METHODS/CONVERTS (and packages/catalog's methods.py/converts.py,
 * which are themselves a port of the same prototype). Kept here, rather than fetched from the
 * API, so the estimate recomputes live as the user edits params with no round trip. */
export const SIZE_ESTIMATORS: Record<string, Estimator> = {
  // ---- quantization ----
  q_fp16: (m) => (m.size * 16) / m.bits,
  q_bf16: (m) => (m.size * 16) / m.bits,
  q_int8_dyn: (m) => (m.size * 8.2) / m.bits,
  q_int8_static: (m) => (m.size * 8.1) / m.bits,
  q_gguf: (m, v) => (m.params * (GGUF_BITS_PER_WEIGHT[String(v.qtype)] ?? 0)) / 8,
  q_gptq: (m, v) => (m.params * (Number(v.bits) + 32 / Number(v.group))) / 8,
  q_awq: (m, v) => (m.params * (4 + 32 / Number(v.group))) / 8,
  q_nf4: (m, v) => (m.params * (v.double ? 4.13 : 4.5)) / 8,

  // ---- pruning ----
  p_magnitude: (m, v) =>
    v.storage === 'dense' ? m.size : m.size * Math.min(1, (1 - Number(v.sparsity) / 100) * 1.3),
  p_structured: (m, v) => m.size * Math.pow(1 - Number(v.ratio) / 100, 1.8),
  p_24: (m) => m.size * 0.56,
  p_wanda: (m, v) =>
    v.pattern === '2:4'
      ? m.size * 0.56
      : m.size * Math.min(1, (1 - Number(v.sparsity) / 100) * 1.3),

  // ---- distillation ----
  d_logit: (m, v) => {
    const share: Record<string, number> = { half_width: 0.25, half_depth: 0.5, compact: 0.15 }
    const s = share[String(v.student)]
    return s === undefined ? null : s * m.size * (32 / m.bits)
  },
  d_feature: (m, v) => {
    const share: Record<string, number> = { half_width: 0.25, half_depth: 0.5 }
    const s = share[String(v.student)]
    return s === undefined ? null : s * m.size * (32 / m.bits)
  },
  d_llm: (m, v) => m.size * (v.student === 'layerdrop' ? 0.5 : 0.4),

  // ---- low-rank ----
  l_svd: (m, v) => {
    const share = (SHARE_OF_LINEAR[m.family] ?? 0) * (v.layers === 'attn' ? 1 : 0.67)
    return m.size * (1 - share * Math.max(0, 1 - 2 * svdRankShare(v)))
  },
  l_tucker: (m, v) => {
    const factor = v.kind === 'cp' ? 1.1 : 1.6
    return m.size * (1 - 0.85 * Math.max(0, 1 - (factor * Number(v.rank)) / 100))
  },

  // ---- convert ----
  c_onnx: (m) => m.size,
  c_tflite: (m, v) => m.size * (v.precision === 'fp16' ? 16 / m.bits : 1),
  c_torchscript: (m) => m.size,
  c_savedmodel: (m) => m.size,
  c_safetensors: (m) => m.size,
  c_gguf: (m, v) => {
    const bits: Record<string, number> = { f32: 32, f16: 16, bf16: 16, q8_0: 8.5 }
    return m.size * ((bits[String(v.outtype)] ?? 16) / m.bits)
  },
  c_openvino: (m, v) => {
    const bits: Record<string, number> = { fp32: 32, fp16: 16, int8: 8.2 }
    return m.size * ((bits[String(v.precision)] ?? 16) / m.bits)
  },
  c_tensorrt: (m, v) => {
    const bits: Record<string, number> = { fp32: 32, fp16: 16, int8: 8.5 }
    return m.size * ((bits[String(v.precision)] ?? 16) / m.bits)
  },
  c_coreml: (m, v) => m.size * ((v.precision === 'fp16' ? 16 : 32) / m.bits),
}

/** Estimated output size in bytes, or null when it can't be estimated yet (e.g. a custom
 * student model) — port of the prototype's `estimateBytes()`. */
export function estimateOutputBytes(
  operationId: string,
  model: ModelInfo,
  values: ParamValues,
): number | null {
  const estimator = SIZE_ESTIMATORS[operationId]
  if (!estimator) return null
  const bytes = estimator(model, values)
  return bytes == null ? null : Math.round(bytes)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1_073_741_824) return `${(bytes / 1_048_576).toFixed(1)} MB`
  return `${(bytes / 1_073_741_824).toFixed(2)} GB`
}

export interface SizeChangeSummary {
  bytes: number
  percent: number
  direction: 'smaller' | 'larger' | 'same'
}

/** Percentage change summary — port of the prototype's `estimateHTML()` math. */
export function summarizeSizeChange(outputBytes: number, originalSize: number): SizeChangeSummary {
  const percent = Math.round((1 - outputBytes / originalSize) * 100)
  const direction = percent > 0 ? 'smaller' : percent < 0 ? 'larger' : 'same'
  return { bytes: outputBytes, percent: Math.abs(percent), direction }
}
