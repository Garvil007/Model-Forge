import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useCancelJob, useCreateJob, useJob } from '../../api/hooks'
import type { ApiJob } from '../../api/types'
import type { ModelInfo, Operation, ParamValues } from '../catalog/types'
import { estimateJobCost, isExpensiveOperation } from './jobConfirmation'

const JOB_PARAM = 'job'

export interface UseJobLifecycleArgs {
  modelId: string | undefined
  model: ModelInfo | undefined
  operation: Operation | undefined
  values: ParamValues
}

/** Owns the run-button-through-result state machine: confirming an expensive job, creating it,
 * polling it (persisting the job id in the URL so a reload restores the progress view),
 * cancelling, and detecting a dropped poll so the UI can show "reconnecting". */
export function useJobLifecycle({ modelId, model, operation, values }: UseJobLifecycleArgs) {
  const [searchParams, setSearchParams] = useSearchParams()
  const jobId = searchParams.get(JOB_PARAM) ?? undefined
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [cancelConfirmOpen, setCancelConfirmOpen] = useState(false)

  const jobQuery = useJob(jobId)
  const createJob = useCreateJob()
  const cancelJob = useCancelJob()

  const setJobId = (id: string | undefined) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set(JOB_PARAM, id)
    else next.delete(JOB_PARAM)
    setSearchParams(next, { replace: true })
  }

  const startJob = () => {
    if (!modelId || !operation) return
    createJob.mutate(
      { modelId, operationId: operation.id, values },
      { onSuccess: (job: ApiJob) => setJobId(job.id) },
    )
  }

  const requestRun = () => {
    if (!operation) return
    if (isExpensiveOperation(operation)) setConfirmOpen(true)
    else startJob()
  }

  const confirmRun = () => {
    setConfirmOpen(false)
    startJob()
  }

  const requestCancel = () => setCancelConfirmOpen(true)
  const confirmCancel = () => {
    setCancelConfirmOpen(false)
    if (jobId) cancelJob.mutate(jobId)
  }

  const retrySameSettings = () => startJob()

  const reset = () => {
    setJobId(undefined)
    createJob.reset()
  }

  const job = jobQuery.data
  const running = job ? job.status === 'running' || job.status === 'queued' : createJob.isPending
  const reconnecting =
    jobQuery.fetchStatus === 'idle' &&
    jobQuery.failureCount > 0 &&
    Boolean(job) &&
    (job!.status === 'running' || job!.status === 'queued')

  const costEstimate = operation && model ? estimateJobCost(operation, model) : null

  return {
    jobId,
    job,
    running,
    reconnecting,
    confirmOpen,
    cancelConfirmOpen,
    costEstimate,
    createError: createJob.error,
    canceling: cancelJob.isPending,
    requestRun,
    confirmRun,
    cancelConfirmDialog: () => setConfirmOpen(false),
    requestCancel,
    confirmCancel,
    cancelCancelDialog: () => setCancelConfirmOpen(false),
    retrySameSettings,
    reset,
  }
}
