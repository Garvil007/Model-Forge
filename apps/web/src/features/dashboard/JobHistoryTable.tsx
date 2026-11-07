import type { ApiJob, ApiModel } from '../../api/types'
import { Badge } from '../../ui/Badge/Badge'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import { Skeleton } from '../../ui/Skeleton/Skeleton'
import { cx } from '../../ui/cx'
import { getOperationById } from '../catalog/types'
import { summarizeSizeChange } from '../catalog/sizeEstimateFormulas'
import styles from './JobHistoryTable.module.css'

export interface JobHistoryTableProps {
  jobs: ApiJob[]
  models: ApiModel[]
  isLoading?: boolean
  isError?: boolean
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onLoadMore?: () => void
  onRerun: (job: ApiJob) => void
  /** Job ids currently picked for the Compare view. */
  selectedIds?: Set<string>
  onToggleSelect?: (job: ApiJob) => void
}

const STATUS_VARIANT: Record<ApiJob['status'], 'lossless' | 'near-lossless' | 'lossy'> = {
  succeeded: 'lossless',
  running: 'near-lossless',
  queued: 'near-lossless',
  failed: 'lossy',
  canceled: 'lossy',
}

function sizeChangeLabel(job: ApiJob, model: ApiModel | undefined): string {
  if (!job.result || !model) return '—'
  const { percent, direction } = summarizeSizeChange(job.result.outputBytes, model.size)
  if (direction === 'same') return 'Same size'
  return `${percent}% ${direction}`
}

function accuracyChangeLabel(job: ApiJob): string {
  if (!job.result) return '—'
  const [first] = Object.values(job.result.metrics)
  return first ?? '—'
}

function costLabel(job: ApiJob): string {
  return job.cost == null ? '—' : `$${job.cost.toFixed(2)}`
}

/** Job history rows — operation, model, status, size/accuracy change and cost, with a
 * compare checkbox (succeeded jobs only) and a "Re-run" action. Cursor-paged via "Load more". */
export function JobHistoryTable({
  jobs,
  models,
  isLoading = false,
  isError = false,
  hasNextPage = false,
  isFetchingNextPage = false,
  onLoadMore,
  onRerun,
  selectedIds,
  onToggleSelect,
}: JobHistoryTableProps) {
  const modelsById = new Map(models.map((m) => [m.id, m]))

  if (isLoading) {
    return (
      <div className={styles.table} aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.row}>
            <Skeleton width="60%" />
            <Skeleton width="20%" />
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return <Notice variant="error">Couldn't load your job history. Try reloading the page.</Notice>
  }

  if (jobs.length === 0) {
    return (
      <div className={styles.empty}>
        <p>No jobs yet — run a compression or conversion to see it here.</p>
      </div>
    )
  }

  return (
    <>
      <div className={styles.table} role="table" aria-label="Job history">
        <div className={cx(styles.row, styles.head)} role="row" aria-hidden="true">
          <span>Compare</span>
          <span>Operation</span>
          <span>Model</span>
          <span>Status</span>
          <span>Size change</span>
          <span>Accuracy change</span>
          <span>Cost</span>
          <span>Date</span>
          <span>Actions</span>
        </div>
        {jobs.map((job) => {
          const model = modelsById.get(job.modelId)
          const operation = getOperationById(job.operationId)
          const canCompare = job.status === 'succeeded'
          return (
            <div key={job.id} className={styles.row} role="row">
              <span role="cell">
                {canCompare && onToggleSelect && (
                  <input
                    type="checkbox"
                    aria-label={`Compare ${operation?.label ?? job.operationId}`}
                    checked={selectedIds?.has(job.id) ?? false}
                    onChange={() => onToggleSelect(job)}
                  />
                )}
              </span>
              <span role="cell">{operation?.label ?? job.operationId}</span>
              <span role="cell">{model?.filename ?? job.modelId}</span>
              <span role="cell">
                <Badge variant={STATUS_VARIANT[job.status]} />
                <span className={styles.statusText}>{job.status}</span>
              </span>
              <span role="cell">{sizeChangeLabel(job, model)}</span>
              <span role="cell">{accuracyChangeLabel(job)}</span>
              <span role="cell">{costLabel(job)}</span>
              <span role="cell">{new Date(job.createdAt).toLocaleDateString()}</span>
              <span role="cell">
                <Button variant="link" onClick={() => onRerun(job)}>
                  Re-run
                </Button>
              </span>
            </div>
          )
        })}
      </div>

      {hasNextPage && (
        <div className={styles.loadMore}>
          <Button variant="secondary" loading={isFetchingNextPage} onClick={onLoadMore}>
            Load more
          </Button>
        </div>
      )}
    </>
  )
}
