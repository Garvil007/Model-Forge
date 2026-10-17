import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import type { JobErrorInfo } from '../../api/types'
import styles from './JobError.module.css'

export interface JobErrorProps {
  error: JobErrorInfo
  /** Re-run the exact same job — only offered for a transient failure (spot interruption). */
  onRetry?: () => void
  /** Go back to the params panel to change something before trying again. */
  onAdjustSettings?: () => void
}

const TITLES: Record<JobErrorInfo['code'], string> = {
  out_of_memory: 'Ran out of memory',
  unsupported_operator: 'Unsupported operator',
  bad_calibration_data: 'Calibration data problem',
  gated_model: 'Model access required',
  quota_exceeded: "You've used your quota",
  spot_interrupted: 'Instance interrupted',
  timeout: 'Job timed out',
  unknown: 'Something went wrong',
}

/** Explains what happened and what to do next — never a raw stack trace. `quota_exceeded` has
 * no retry action (nothing on this job can be adjusted to fix it); `spot_interrupted` offers an
 * identical-settings retry since nothing about the job itself was wrong; everything else offers
 * "retry with adjusted settings" so the user goes back to the params panel first. */
export function JobError({ error, onRetry, onAdjustSettings }: JobErrorProps) {
  return (
    <Notice variant="error">
      <strong>{TITLES[error.code]}</strong>
      <p>{error.message}</p>
      <div className={styles.actions}>
        {error.code === 'spot_interrupted' && onRetry && (
          <Button variant="link" onClick={onRetry}>
            Retry
          </Button>
        )}
        {error.code !== 'spot_interrupted' &&
          error.code !== 'quota_exceeded' &&
          onAdjustSettings && (
            <Button variant="link" onClick={onAdjustSettings}>
              Retry with adjusted settings
            </Button>
          )}
      </div>
    </Notice>
  )
}
