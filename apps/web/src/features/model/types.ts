import type { ModelFamily } from '../../api/types'

/** A model detected client-side from a file or a sample, before it's registered with the API
 * (that's `ApiModel`, in `api/types.ts`) — mirrors `docs/ui-prototype.html`'s model object. */
export interface DetectedModel {
  filename: string
  format: string
  family: ModelFamily
  bits: number
  params: number
  size: number
  inputs: string | null
  metric: [name: string, base: number, unit: string] | null
}

export type SampleKey = 'resnet' | 'llama' | 'yolo' | 'mobilenet'

export interface UploadProgressState {
  status: 'idle' | 'uploading' | 'paused' | 'completing' | 'done' | 'error'
  bytesUploaded: number
  totalBytes: number
  bytesPerSecond: number
  /** Seconds, or null before enough samples exist to estimate. */
  secondsRemaining: number | null
  error: string | null
}
