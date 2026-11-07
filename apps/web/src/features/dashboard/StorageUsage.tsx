import { Notice } from '../../ui/Notice/Notice'
import { Skeleton } from '../../ui/Skeleton/Skeleton'
import { formatBytes } from '../catalog/sizeEstimateFormulas'
import styles from './StorageUsage.module.css'

export interface StorageUsageProps {
  usedBytes: number
  limitBytes: number
  retentionDays: number
  isLoading?: boolean
  isError?: boolean
}

/** Storage used against the plan limit, with a note about how long results and uploads are
 * kept before the retention TTL deletes them. */
export function StorageUsage({
  usedBytes,
  limitBytes,
  retentionDays,
  isLoading = false,
  isError = false,
}: StorageUsageProps) {
  if (isLoading) {
    return (
      <div className={styles.wrap} aria-busy="true">
        <Skeleton width="40%" />
        <Skeleton height="12px" />
      </div>
    )
  }

  if (isError) {
    return <Notice variant="error">Couldn't load your storage usage.</Notice>
  }

  const percent = limitBytes > 0 ? Math.min(100, Math.round((usedBytes / limitBytes) * 100)) : 0

  return (
    <div className={styles.wrap}>
      <div className={styles.headline}>
        <span>Storage</span>
        <span>
          {formatBytes(usedBytes)} of {formatBytes(limitBytes)} used
        </span>
      </div>
      <div
        className={styles.track}
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={styles.fill} style={{ width: `${percent}%` }} />
      </div>
      <p className={styles.note}>
        Uploaded models and job results are kept for {retentionDays} days, then deleted
        automatically.
      </p>
    </div>
  )
}
