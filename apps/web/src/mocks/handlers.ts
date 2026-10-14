import { delay, http, HttpResponse } from 'msw'
import catalogJson from '../features/catalog/generated/catalog.json'
import type {
  ApiErrorBody,
  ApiJob,
  ApiModel,
  CompleteUploadRequest,
  CreateJobRequest,
  CreateUploadRequest,
  CreateUploadResponse,
  ImportHfRequest,
  JobErrorInfo,
  JobStage,
} from '../api/types'
import { getOperationById, type ParamValues } from '../features/catalog/types'
import { HF_REPOS } from './data'
import { initialStages, jobs, makeId, models, uploads, type JobRecord } from './db'
import { stageDurationMs, stagesForOperation, totalDurationMs, type JobStageDef } from './jobStages'
import { getScenarios, type JobErrorScenario } from './scenarios'

const UPLOAD_PART_SIZE = 8 * 1024 * 1024
const BASE_DELAY_MS = 150
const SLOW_NETWORK_EXTRA_MS = 1800

function errorBody(code: string, message: string): ApiErrorBody {
  return { error: { code, message } }
}

async function simulateLatency(extra = 0): Promise<void> {
  const scenarios = getScenarios()
  await delay(BASE_DELAY_MS + extra + (scenarios.slowNetwork ? SLOW_NETWORK_EXTRA_MS : 0))
}

/** Checked first in every handler — the expired-session scenario should block everything. */
function sessionExpiredResponse(): Response | null {
  if (!getScenarios().expiredSession) return null
  return HttpResponse.json(
    errorBody('session_expired', 'Your session has expired. Sign in again.'),
    {
      status: 401,
    },
  )
}

const JOB_ERROR_INFO: Record<Exclude<JobErrorScenario, 'none'>, JobErrorInfo> = {
  out_of_memory: {
    code: 'out_of_memory',
    message:
      'The worker ran out of memory while processing this model. Try a smaller batch size, a lighter method, or a larger instance.',
  },
  unsupported_operator: {
    code: 'unsupported_operator',
    operator: 'aten::_scaled_dot_product_flash_attention',
    message:
      "This model uses the operator aten::_scaled_dot_product_flash_attention, which this conversion target doesn't support yet.",
  },
  bad_calibration_data: {
    code: 'bad_calibration_data',
    message:
      "Your calibration data couldn't be used — check that it's unlabeled example inputs in the format this operation expects, then try again.",
  },
  gated_model: {
    code: 'gated_model',
    message:
      "This model's weights are gated and the access token on file doesn't have permission to run this operation.",
  },
  spot_interrupted: {
    code: 'spot_interrupted',
    message:
      'The spot instance running this job was reclaimed partway through. No progress is lost — retry to pick up a new instance.',
  },
}

function buildStages(stageDefs: JobStageDef[], elapsed: number): JobStage[] {
  let consumed = 0
  return stageDefs.map((stage) => {
    const duration = stageDurationMs(stage)
    const stageStart = consumed
    consumed += duration
    const status: JobStage['status'] =
      elapsed >= consumed ? 'done' : elapsed >= stageStart ? 'active' : 'pending'
    if (!stage.epochs) return { label: stage.label, status }
    const withinStage = Math.max(0, elapsed - stageStart)
    const epoch =
      status === 'done'
        ? stage.epochs
        : status === 'active'
          ? Math.min(stage.epochs, Math.floor(withinStage / EPOCH_DURATION_MS))
          : 0
    return { label: stage.label, status, epoch, totalEpochs: stage.epochs }
  })
}

const EPOCH_DURATION_MS = 60

function advanceJob(job: JobRecord): JobRecord {
  if (job.status === 'succeeded' || job.status === 'failed' || job.status === 'canceled') return job

  const elapsed = Date.now() - job.startedAt
  const totalDuration = totalDurationMs(job.stageDefs)
  const stages = buildStages(job.stageDefs, Math.min(elapsed, totalDuration))

  if (elapsed < totalDuration) {
    job.status = 'running'
    job.stages = stages
    return job
  }

  job.stages = stages
  const errorKind = getScenarios().jobErrorKind
  if (errorKind !== 'none') {
    job.status = 'failed'
    job.error = JOB_ERROR_INFO[errorKind]
    job.result = null
  } else {
    job.status = 'succeeded'
    job.error = null
    const model = models.get(job.modelId)
    const outputBytes = Math.round((model?.size ?? 1_000_000) * 0.4)
    const hasValidation = Boolean(model?.validationFilename) || Boolean(model?.metric)
    const metrics: Record<string, string> = hasValidation
      ? { [model?.metric?.[0] ?? 'Accuracy']: '91.2% (was 91.4%)' }
      : { 'Output similarity': '0.99812' }
    job.result = {
      outputBytes,
      downloadName: `${job.modelId}_${job.operationId}.bin`,
      metrics,
      measuredOnValidation: hasValidation,
      speedNote: null,
    }
  }
  return job
}

export const handlers = [
  http.get('/api/catalog', async () => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    await simulateLatency()
    return HttpResponse.json(catalogJson)
  }),

  http.post('/api/uploads', async ({ request }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    const body = (await request.json()) as CreateUploadRequest
    await simulateLatency()
    if (!body.filename || !body.size || body.size <= 0) {
      return HttpResponse.json(
        errorBody('invalid_request', 'filename and a positive size are required.'),
        {
          status: 400,
        },
      )
    }
    const id = makeId('upload')
    const totalParts = Math.max(1, Math.ceil(body.size / UPLOAD_PART_SIZE))
    uploads.set(id, {
      id,
      key: `uploads/${id}/${body.filename}`,
      filename: body.filename,
      size: body.size,
      partSize: UPLOAD_PART_SIZE,
      totalParts,
      partAttempts: new Map(),
      receivedParts: new Set(),
      completed: false,
    })
    const response: CreateUploadResponse = {
      uploadId: id,
      key: uploads.get(id)!.key,
      partSize: UPLOAD_PART_SIZE,
      totalParts,
      partUrls: Array.from({ length: totalParts }, (_, i) => `/api/uploads/${id}/parts/${i + 1}`),
    }
    return HttpResponse.json(response, { status: 201 })
  }),

  http.put('/api/uploads/:uploadId/parts/:partNumber', async ({ params }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    const uploadId = String(params.uploadId)
    const partNumber = Number(params.partNumber)
    const upload = uploads.get(uploadId)
    if (!upload) {
      return HttpResponse.json(errorBody('upload_not_found', 'Unknown upload.'), { status: 404 })
    }

    const attempts = (upload.partAttempts.get(partNumber) ?? 0) + 1
    upload.partAttempts.set(partNumber, attempts)

    const scenarios = getScenarios()
    const shouldFail = scenarios.uploadFailPart === partNumber && attempts <= 2
    await simulateLatency(shouldFail ? 0 : 60)
    if (shouldFail) {
      return HttpResponse.json(
        errorBody('part_upload_failed', `Part ${partNumber} failed to upload.`),
        {
          status: 500,
        },
      )
    }

    upload.receivedParts.add(partNumber)
    return new HttpResponse(null, { status: 200, headers: { ETag: `"part-${partNumber}"` } })
  }),

  http.post('/api/uploads/:uploadId/complete', async ({ request, params }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    const uploadId = String(params.uploadId)
    const upload = uploads.get(uploadId)
    if (!upload) {
      return HttpResponse.json(errorBody('upload_not_found', 'Unknown upload.'), { status: 404 })
    }
    const body = (await request.json()) as CompleteUploadRequest
    await simulateLatency()
    if (upload.receivedParts.size < upload.totalParts) {
      return HttpResponse.json(
        errorBody(
          'incomplete_upload',
          `Only ${upload.receivedParts.size} of ${upload.totalParts} parts were received.`,
        ),
        { status: 400 },
      )
    }
    upload.completed = true

    const id = makeId('model')
    const model: ApiModel = {
      id,
      ...body.model,
      validationFilename: null,
      source: 'upload',
      repoId: null,
      createdAt: new Date().toISOString(),
    }
    models.set(id, model)
    return HttpResponse.json(model, { status: 201 })
  }),

  http.post('/api/models/import-hf', async ({ request }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    const body = (await request.json()) as ImportHfRequest
    const fixture = HF_REPOS.find((repo) => repo.repoId === body.repoId)
    await simulateLatency(1000)
    if (!fixture) {
      return HttpResponse.json(
        errorBody('repo_not_found', `No repository "${body.repoId}" was found on Hugging Face.`),
        { status: 404 },
      )
    }
    if (fixture.gated && !body.token) {
      return HttpResponse.json(
        errorBody(
          'gated_repo',
          'This repository is gated. Provide an access token with permission to use it.',
        ),
        { status: 403 },
      )
    }
    const id = makeId('model')
    const model: ApiModel = {
      id,
      ...fixture.model,
      validationFilename: null,
      source: 'huggingface',
      repoId: fixture.repoId,
      createdAt: new Date().toISOString(),
    }
    models.set(id, model)
    return HttpResponse.json(model, { status: 201 })
  }),

  http.get('/api/models', async () => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    await simulateLatency()
    const list = [...models.values()].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    return HttpResponse.json(list)
  }),

  http.get('/api/models/:id', async ({ params }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    await simulateLatency()
    const model = models.get(String(params.id))
    if (!model) {
      return HttpResponse.json(errorBody('model_not_found', 'Unknown model.'), { status: 404 })
    }
    return HttpResponse.json(model)
  }),

  http.post('/api/jobs', async ({ request }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    const scenarios = getScenarios()
    if (scenarios.quotaExceeded) {
      await simulateLatency()
      return HttpResponse.json(
        errorBody(
          'quota_exceeded',
          "You've used all of your plan's compute quota for this period.",
        ),
        { status: 403 },
      )
    }
    const body = (await request.json()) as CreateJobRequest
    if (!models.has(body.modelId)) {
      return HttpResponse.json(errorBody('model_not_found', 'Unknown model.'), { status: 404 })
    }
    const operation = getOperationById(body.operationId)
    if (!operation) {
      return HttpResponse.json(errorBody('operation_not_found', 'Unknown operation.'), {
        status: 404,
      })
    }
    await simulateLatency()
    const id = makeId('job')
    const stageDefs = stagesForOperation(operation, body.values as ParamValues)
    const job: JobRecord = {
      id,
      modelId: body.modelId,
      operationId: body.operationId,
      values: body.values,
      status: 'running',
      stages: initialStages(stageDefs),
      createdAt: new Date().toISOString(),
      result: null,
      error: null,
      startedAt: Date.now(),
      canceled: false,
      stageDefs,
    }
    jobs.set(id, job)
    return HttpResponse.json(job as ApiJob, { status: 201 })
  }),

  http.get('/api/jobs/:id', async ({ params }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    await simulateLatency()
    const job = jobs.get(String(params.id))
    if (!job) {
      return HttpResponse.json(errorBody('job_not_found', 'Unknown job.'), { status: 404 })
    }
    return HttpResponse.json(advanceJob(job) as ApiJob)
  }),

  http.post('/api/jobs/:id/cancel', async ({ params }) => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    await simulateLatency()
    const job = jobs.get(String(params.id))
    if (!job) {
      return HttpResponse.json(errorBody('job_not_found', 'Unknown job.'), { status: 404 })
    }
    if (job.status !== 'succeeded' && job.status !== 'failed') {
      job.canceled = true
      job.status = 'canceled'
    }
    return HttpResponse.json(job as ApiJob)
  }),

  http.get('/api/jobs', async () => {
    const expired = sessionExpiredResponse()
    if (expired) return expired
    await simulateLatency()
    const list = [...jobs.values()]
      .map((job) => advanceJob(job))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    return HttpResponse.json(list as ApiJob[])
  }),
]
