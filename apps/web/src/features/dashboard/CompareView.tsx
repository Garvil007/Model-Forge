import type { ApiJob, ApiModel } from '../../api/types'
import { Notice } from '../../ui/Notice/Notice'
import { getOperationById } from '../catalog/types'
import { summarizeSizeChange, formatBytes } from '../catalog/sizeEstimateFormulas'
import styles from './CompareView.module.css'

export interface CompareViewProps {
  model: ApiModel
  /** Succeeded jobs run against `model` — picked for comparison by the caller (e.g. checkboxes
   * in the job history table). Only `succeeded` jobs with a `result` are rendered. */
  jobs: ApiJob[]
}

/** Side-by-side comparison of several results run against the same original model: size,
 * accuracy and a latency note per job, plus a small bar chart of the size reduction. */
export function CompareView({ model, jobs }: CompareViewProps) {
  const comparable = jobs.filter((job) => job.status === 'succeeded' && job.result)

  if (comparable.length < 2) {
    return (
      <Notice variant="info">
        Pick at least two succeeded jobs from the job history to compare them.
      </Notice>
    )
  }

  const rows = comparable.map((job) => {
    const result = job.result!
    const change = summarizeSizeChange(result.outputBytes, model.size)
    const operation = getOperationById(job.operationId)
    const [accuracyChange] = Object.values(result.metrics)
    return {
      job,
      label: operation?.label ?? job.operationId,
      beforeBytes: model.size,
      afterBytes: result.outputBytes,
      percent: change.percent,
      direction: change.direction,
      accuracyChange: accuracyChange ?? '—',
      latencyNote: result.speedNote ?? '—',
    }
  })

  const maxPercent = Math.max(1, ...rows.map((row) => Math.abs(row.percent)))

  return (
    <div className={styles.wrap}>
      <h3 className={styles.heading}>Size reduction</h3>
      <div className={styles.chart}>
        {rows.map((row) => (
          <div key={row.job.id} className={styles.chartRow}>
            <span className={styles.chartLabel}>{row.label}</span>
            <span className={styles.chartTrack}>
              <span
                className={styles.chartFill}
                style={{ width: `${(Math.abs(row.percent) / maxPercent) * 100}%` }}
              />
            </span>
            <span className={styles.chartValue}>
              {row.direction === 'same' ? 'Same size' : `${row.percent}% ${row.direction}`}
            </span>
          </div>
        ))}
      </div>

      <div className={styles.table} role="table" aria-label="Compare results">
        <div className={styles.row} role="row">
          <span className={styles.rowHead}>Technique</span>
          <span className={styles.rowHead}>Size</span>
          <span className={styles.rowHead}>Accuracy change</span>
          <span className={styles.rowHead}>Latency</span>
        </div>
        {rows.map((row) => (
          <div key={row.job.id} className={styles.row} role="row">
            <span role="cell">{row.label}</span>
            <span role="cell">
              {formatBytes(row.beforeBytes)} → {formatBytes(row.afterBytes)}
            </span>
            <span role="cell">{row.accuracyChange}</span>
            <span role="cell">{row.latencyNote}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
