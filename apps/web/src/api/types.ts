/** Shared request/response DTOs for the ModelForge API — hand-written now since `apps/api` has no
 * routes yet; these are what `src/mocks` serves and what `src/api/client.ts`'s hooks expect. Once
 * the real API exists it should be made to match this file, not the other way around. */

export type ModelFamily = 'vision' | 'llm' | 'other'
export type ModelSource = 'upload' | 'huggingface'

export interface ApiModel {
  id: string
  filename: string
  format: string
  family: ModelFamily
  bits: number
  params: number
  size: number
  inputs: string | null
  metric: [name: string, base: number, unit: string] | null
  validationFilename: string | null
  source: ModelSource
  repoId: string | null
  createdAt: string
  /** Set by the real API once a model exists server-side (upload/import always start at
   * "checking"/"importing" — the mock omits this, so callers should treat it as optional). */
  status?: 'importing' | 'checking' | 'ready' | 'failed'
  detectionError?: { code: string; message: string } | null
}

export interface CreateUploadRequest {
  filename: string
  size: number
}

export interface CreateUploadResponse {
  uploadId: string
  key: string
  partSize: number
  totalParts: number
  partUrls: string[]
}

export interface CompleteUploadRequest {
  uploadId: string
  /** Detected client-side (see `features/model/detectFormat.ts`) — the server just registers it. */
  model: {
    filename: string
    format: string
    family: ModelFamily
    bits: number
    params: number
    size: number
    inputs: string | null
    metric: [name: string, base: number, unit: string] | null
  }
}

export interface ImportHfRequest {
  repoId: string
  token?: string
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'

export interface JobStage {
  label: string
  status: 'pending' | 'active' | 'done'
  /** Set only on a training-style stage (distillation, or fine-tuning after pruning/low-rank). */
  epoch?: number
  totalEpochs?: number
}

export interface JobResult {
  outputBytes: number
  downloadName: string
  /** Metric label -> rendered value, e.g. {"Top-1 accuracy": "75.8% (was 76.1%)"}. */
  metrics: Record<string, string>
  /** True when `metrics` reflects the model's own validation data rather than a similarity proxy. */
  measuredOnValidation: boolean
  speedNote: string | null
}

/** Job-terminal failures the worker can report — each maps to one explanation in `JobError`. */
export type JobErrorCode =
  | 'out_of_memory'
  | 'unsupported_operator'
  | 'bad_calibration_data'
  | 'gated_model'
  | 'quota_exceeded'
  | 'gpu_kill_switch'
  | 'spot_interrupted'
  | 'timeout'
  | 'unknown'

export interface JobErrorInfo {
  code: JobErrorCode
  message: string
  /** Set only for `unsupported_operator` — the specific op that couldn't be converted. */
  operator?: string
}

export interface ApiJob {
  id: string
  modelId: string
  operationId: string
  values: Record<string, unknown>
  status: JobStatus
  stages: JobStage[]
  createdAt: string
  result: JobResult | null
  error: JobErrorInfo | null
  /** USD, dashboard-only — the actual cost once known, falling back to the pre-run estimate. */
  cost: number | null
}

export type JobHistoryFilters = {
  status?: JobStatus
  /** An operation id, e.g. "q_int8_static" — "technique" in the UI's own words. */
  operationId?: string
  dateFrom?: string
  dateTo?: string
}

export interface PaginatedJobs {
  items: ApiJob[]
  /** Opaque DynamoDB `LastEvaluatedKey` cursor; null once there are no more pages. */
  nextCursor: string | null
}

export interface CreateJobRequest {
  modelId: string
  operationId: string
  values: Record<string, unknown>
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
  }
}

/** GET /usage — remaining monthly CPU/GPU compute quota, for the dashboard's quota display. */
export interface ApiUsage {
  plan: string
  cpuSecondsUsed: number
  cpuSecondsLimit: number
  gpuSecondsUsed: number
  gpuSecondsLimit: number
  maxConcurrentJobs: number
  gpuKillSwitchOn: boolean
  storageBytesUsed: number
  storageBytesLimit: number
  retentionDays: number
}

export interface NotificationSettings {
  jobCompleteEmail: boolean
  weeklyDigestEmail: boolean
}

/** GET /settings — everything the Settings page needs besides the profile (from `useAuth`). */
export interface ApiSettings {
  notifications: NotificationSettings
  hasHfToken: boolean
}

export interface UpdateNotificationsRequest {
  notifications: NotificationSettings
}

export interface SetHfTokenRequest {
  token: string
}

/** GET /billing/plans — display data for the `/pricing` page. */
export interface ApiBillingPlan {
  id: string
  name: string
  monthlyPriceUsdCents: number
  tagline: string
  features: string[]
}

/** POST /billing/checkout-session and /billing/portal-session both just hand back a
 * Stripe-hosted URL to redirect the browser to — plan changes only ever happen via the
 * webhook, once Stripe confirms them. */
export interface BillingRedirect {
  url: string
}

export interface DeleteAccountRequest {
  /** The user must type this exact word to enable the request — enforced client-side; the
   * server re-checks it so a forged request can't skip the confirmation either. */
  confirm: 'DELETE'
}
