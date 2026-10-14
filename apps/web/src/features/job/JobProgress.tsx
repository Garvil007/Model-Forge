import { cx } from '../../ui/cx'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import { Spinner } from '../../ui/Spinner/Spinner'
import type { JobStage } from '../../api/types'
import { formatDuration } from '../model/format'
import styles from './JobProgress.module.css'

export interface JobProgressProps {
  stages: JobStage[]
  elapsedSeconds: number
  /** True once polling has failed and we're waiting to retry — shown instead of hiding progress. */
  reconnecting: boolean
  onCancel: () => void
  canceling?: boolean
}

/** The staged checklist shown while a job runs — done/active/pending dots, a per-epoch bar on
 * training-style stages, elapsed time, and cancel. Port of the prototype's `draw()`. */
export function JobProgress({
  stages,
  elapsedSeconds,
  reconnecting,
  onCancel,
  canceling,
}: JobProgressProps) {
  return (
    <div className={styles.panel} role="group" aria-label="Job progress">
      <div className={styles.header}>
        <span className={styles.elapsed}>Elapsed: {formatDuration(elapsedSeconds)}</span>
      </div>

      {reconnecting && (
        <Notice variant="warning" className={styles.reconnecting}>
          <Spinner size="sm" />
          Reconnecting… checking on your job again.
        </Notice>
      )}

      <ol className={styles.stages}>
        {stages.map((stage) => (
          <li key={stage.label} className={cx(styles.stage, styles[stage.status])}>
            <span className={styles.dot} aria-hidden="true" />
            <span>{stage.label}</span>
            {stage.totalEpochs != null && stage.status !== 'pending' && (
              <>
                <span className={styles.epoch}>
                  <span
                    className={styles.epochFill}
                    style={{ width: `${((stage.epoch ?? 0) / stage.totalEpochs) * 100}%` }}
                  />
                </span>
                <span className={styles.epochLabel}>
                  epoch {stage.epoch ?? 0} of {stage.totalEpochs}
                </span>
              </>
            )}
          </li>
        ))}
      </ol>

      <div className={styles.actions}>
        <Button variant="secondary" onClick={onCancel} disabled={canceling}>
          Cancel job
        </Button>
      </div>
    </div>
  )
}
