/** Dev-only toggles read by `src/mocks/handlers.ts` to simulate failure modes without touching
 * handler code — flipped by `ScenarioPanel`, persisted to `sessionStorage` so a reload during
 * manual testing doesn't lose the toggle. */

/** Job-run failure modes the mock worker can simulate — 'none' means the job always succeeds. */
export type JobErrorScenario =
  | 'none'
  | 'out_of_memory'
  | 'unsupported_operator'
  | 'bad_calibration_data'
  | 'gated_model'
  | 'spot_interrupted'

export interface MockScenarios {
  /** Adds extra latency to every handler. */
  slowNetwork: boolean
  /** The given 1-based upload part number fails its first two PUT attempts, then succeeds. 0 disables. */
  uploadFailPart: number
  /** Jobs run their stages normally but finish `failed` with this error instead of `succeeded`. */
  jobErrorKind: JobErrorScenario
  /** `POST /api/jobs` returns 403 quota_exceeded instead of creating a job. */
  quotaExceeded: boolean
  /** Every handler returns 401 unauthorized, as if the session had expired. */
  expiredSession: boolean
}

export const DEFAULT_SCENARIOS: MockScenarios = {
  slowNetwork: false,
  uploadFailPart: 0,
  jobErrorKind: 'none',
  quotaExceeded: false,
  expiredSession: false,
}

const STORAGE_KEY = 'modelforge.mockScenarios'

function readStoredScenarios(): MockScenarios {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_SCENARIOS }
    return { ...DEFAULT_SCENARIOS, ...(JSON.parse(raw) as Partial<MockScenarios>) }
  } catch {
    return { ...DEFAULT_SCENARIOS }
  }
}

let scenarios: MockScenarios = readStoredScenarios()
const listeners = new Set<(scenarios: MockScenarios) => void>()

export function getScenarios(): MockScenarios {
  return scenarios
}

export function setScenarios(patch: Partial<MockScenarios>): void {
  scenarios = { ...scenarios, ...patch }
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(scenarios))
  } catch {
    // Storage can throw in private browsing or when disabled — the in-memory value still applies.
  }
  listeners.forEach((listener) => listener(scenarios))
}

export function resetScenarios(): void {
  scenarios = { ...DEFAULT_SCENARIOS }
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // See setScenarios.
  }
  listeners.forEach((listener) => listener(scenarios))
}

export function subscribeScenarios(listener: (scenarios: MockScenarios) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
