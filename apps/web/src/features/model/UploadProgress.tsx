import { Button } from '../../ui/Button/Button'
import { formatBytes, formatDuration, formatSpeed } from './format'
import styles from './UploadProgress.module.css'
import type { UploadProgressState } from './types'

export interface UploadProgressProps {
  state: UploadProgressState
  onPause: () => void
  onResume: () => void
  onCancel: () => void
}

/** The upload progress bar — percent, speed, ETA, and pause/resume/cancel, shown while
 * `state.status` is `'uploading'`, `'paused'` or `'completing'`. */
export function UploadProgress({ state, onPause, onResume, onCancel }: UploadProgressProps) {
  const percent =
    state.totalBytes > 0
      ? Math.min(100, Math.round((state.bytesUploaded / state.totalBytes) * 100))
      : 0

  return (
    <div className={styles.progress} role="group" aria-label="Upload progress">
      <div className={styles.bar}>
        <div className={styles.barFill} style={{ width: `${percent}%` }} />
      </div>
      <div className={styles.row}>
        <span>
          {formatBytes(state.bytesUploaded)} of {formatBytes(state.totalBytes)} ({percent}%)
        </span>
        {state.status === 'uploading' && (
          <span>
            {formatSpeed(state.bytesPerSecond)}
            {state.secondsRemaining != null && ` — ${formatDuration(state.secondsRemaining)} left`}
          </span>
        )}
        {state.status === 'completing' && <span>Finishing up…</span>}
      </div>
      <div className={styles.actions}>
        {state.status === 'uploading' && (
          <Button variant="secondary" onClick={onPause}>
            Pause
          </Button>
        )}
        {state.status === 'paused' && (
          <Button variant="secondary" onClick={onResume}>
            Resume
          </Button>
        )}
        {(state.status === 'uploading' || state.status === 'paused') && (
          <Button variant="link" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </div>
  )
}
