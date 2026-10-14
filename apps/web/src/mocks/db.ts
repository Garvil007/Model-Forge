import type { ApiJob, ApiModel, JobStage } from '../api/types'
import type { JobStageDef } from './jobStages'

/** In-memory state for the mock backend — reset on every page load / test file, which is fine
 * since nothing here needs to survive a reload. */

export const models = new Map<string, ApiModel>()

export interface UploadRecord {
  id: string
  key: string
  filename: string
  size: number
  partSize: number
  totalParts: number
  /** 1-based part number -> number of PUT attempts seen so far. */
  partAttempts: Map<number, number>
  receivedParts: Set<number>
  completed: boolean
}

export const uploads = new Map<string, UploadRecord>()

export interface JobRecord extends ApiJob {
  /** ms timestamp the job started running; stage progress is derived from elapsed time. */
  startedAt: number
  canceled: boolean
  /** The operation-specific stage list computed at creation time (see `jobStages.ts`). */
  stageDefs: JobStageDef[]
}

export const jobs = new Map<string, JobRecord>()

let nextId = 1
export function makeId(prefix: string): string {
  return `${prefix}_${nextId++}`
}

export function initialStages(stageDefs: JobStageDef[]): JobStage[] {
  return stageDefs.map((stage, i) => ({
    label: stage.label,
    status: i === 0 ? 'active' : 'pending',
    ...(stage.epochs ? { epoch: i === 0 ? 0 : undefined, totalEpochs: stage.epochs } : {}),
  }))
}

export function resetDb(): void {
  models.clear()
  uploads.clear()
  jobs.clear()
  nextId = 1
}
