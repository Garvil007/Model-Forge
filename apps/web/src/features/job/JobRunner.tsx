import { useState } from 'react'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import type { ApiError } from '../../api/client'
import type { ApiModel, JobErrorInfo } from '../../api/types'
import type { ModelInfo, Operation, ParamValues } from '../catalog/types'
import { ConfirmDialog } from './ConfirmDialog'
import { JobError } from './JobError'
import { JobProgress } from './JobProgress'
import styles from './JobRunner.module.css'
import { ResultPanel } from './ResultPanel'
import { RunButton } from './RunButton'
import { buildSizeRuler, downloadFilename, speedNoteFor } from './resultFormulas'
import { runButtonState, type JobTab } from './runButtonLabel'
import { useElapsedSeconds } from './useElapsedSeconds'
import { useJobLifecycle } from './useJobLifecycle'

export interface JobRunnerProps {
  tab: JobTab
  model: ApiModel
  operation: Operation
  values: ParamValues
}

function errorFromApiError(error: ApiError): JobErrorInfo {
  return {
    code: error.code === 'quota_exceeded' ? 'quota_exceeded' : 'unknown',
    message: error.message,
  }
}

/** Composes the whole job lifecycle — run button, expensive-job confirmation, staged progress,
 * result, and taught error states — against one model/operation/values selection. */
export function JobRunner({ tab, model, operation, values }: JobRunnerProps) {
  const [downloadNotice, setDownloadNotice] = useState(false)
  const lifecycle = useJobLifecycle({
    modelId: model.id,
    model: model as ModelInfo,
    operation,
    values,
  })
  const { job } = lifecycle
  const elapsedSeconds = useElapsedSeconds(
    job ? new Date(job.createdAt).getTime() : null,
    lifecycle.running,
  )

  const runState = runButtonState(tab, operation, model, values, lifecycle.running)
  const creationError = lifecycle.createError
    ? errorFromApiError(lifecycle.createError as ApiError)
    : null

  return (
    <div className={styles.runner}>
      {!job && (
        <RunButton {...runState} running={lifecycle.running} onClick={lifecycle.requestRun} />
      )}

      {lifecycle.confirmOpen && lifecycle.costEstimate && (
        <ConfirmDialog
          title="This job runs on a GPU / takes a while"
          body={`Running "${operation.label}" on your model will take some time and cost real money.`}
          meta={[
            `Estimated time: ${lifecycle.costEstimate.time}`,
            `Estimated cost: ${lifecycle.costEstimate.cost}`,
          ]}
          confirmLabel="Start job"
          onConfirm={lifecycle.confirmRun}
          onCancel={lifecycle.cancelConfirmDialog}
        />
      )}

      {lifecycle.cancelConfirmOpen && (
        <ConfirmDialog
          title="Cancel this job?"
          body="Progress made so far will be discarded."
          confirmLabel="Cancel job"
          cancelLabel="Keep running"
          onConfirm={lifecycle.confirmCancel}
          onCancel={lifecycle.cancelCancelDialog}
        />
      )}

      {creationError && <JobError error={creationError} />}

      {job && (job.status === 'running' || job.status === 'queued') && (
        <JobProgress
          stages={job.stages}
          elapsedSeconds={elapsedSeconds}
          reconnecting={lifecycle.reconnecting}
          onCancel={lifecycle.requestCancel}
          canceling={lifecycle.canceling}
        />
      )}

      {job && job.status === 'succeeded' && job.result && (
        <ResultPanel
          headline={buildSizeRuler(model, job.result.outputBytes).headline}
          operationLabel={operation.label}
          speedNote={speedNoteFor(operation, values)}
          beforeBytes={buildSizeRuler(model, job.result.outputBytes).beforeBytes}
          afterBytes={buildSizeRuler(model, job.result.outputBytes).afterBytes}
          beforeWidthPercent={buildSizeRuler(model, job.result.outputBytes).beforeWidthPercent}
          afterWidthPercent={buildSizeRuler(model, job.result.outputBytes).afterWidthPercent}
          metrics={Object.entries(job.result.metrics).map(([label, value]) => ({ label, value }))}
          measuredOnValidation={job.result.measuredOnValidation}
          downloadName={downloadFilename(model, operation, values, tab === 'convert')}
          onDownload={() => setDownloadNotice(true)}
          onTryOtherSettings={lifecycle.reset}
        />
      )}
      {downloadNotice && (
        <Notice variant="info">Downloads are available once the backend is connected.</Notice>
      )}

      {job && job.status === 'failed' && job.error && (
        <JobError
          error={job.error}
          onRetry={lifecycle.retrySameSettings}
          onAdjustSettings={lifecycle.reset}
        />
      )}

      {job && job.status === 'canceled' && (
        <Notice variant="warning">
          Job canceled.
          <div>
            <Button variant="link" onClick={lifecycle.reset}>
              Try other settings
            </Button>
          </div>
        </Notice>
      )}
    </div>
  )
}
