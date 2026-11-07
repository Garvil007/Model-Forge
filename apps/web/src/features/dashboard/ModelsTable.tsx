import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { ApiModel } from '../../api/types'
import { Button } from '../../ui/Button/Button'
import { Skeleton } from '../../ui/Skeleton/Skeleton'
import { Notice } from '../../ui/Notice/Notice'
import { cx } from '../../ui/cx'
import { ConfirmDialog } from '../job/ConfirmDialog'
import { formatBytes } from '../model/format'
import styles from './ModelsTable.module.css'

export interface ModelsTableProps {
  models: ApiModel[]
  isLoading?: boolean
  isError?: boolean
  onCompress: (model: ApiModel) => void
  onConvert: (model: ApiModel) => void
  onDownload: (model: ApiModel) => void
  onDelete: (model: ApiModel) => void
}

/** "My models" — format/size/date, with compress/convert/download/delete actions, an empty
 * state pointing at the upload flow, and loading/error states for the `useModels` query. */
export function ModelsTable({
  models,
  isLoading = false,
  isError = false,
  onCompress,
  onConvert,
  onDownload,
  onDelete,
}: ModelsTableProps) {
  const [pendingDelete, setPendingDelete] = useState<ApiModel | null>(null)

  if (isLoading) {
    return (
      <div className={styles.table} aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.row}>
            <Skeleton width="40%" />
            <Skeleton width="20%" />
            <Skeleton width="20%" />
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return <Notice variant="error">Couldn't load your models. Try reloading the page.</Notice>
  }

  if (models.length === 0) {
    return (
      <div className={styles.empty}>
        <p>No models yet.</p>
        <Link to="/app">Upload a model</Link>
      </div>
    )
  }

  return (
    <>
      <div className={styles.table} role="table" aria-label="My models">
        <div className={cx(styles.row, styles.head)} role="row" aria-hidden="true">
          <span>Model</span>
          <span>Format</span>
          <span>Size</span>
          <span>Uploaded</span>
          <span>Actions</span>
        </div>
        {models.map((model) => (
          <div key={model.id} className={styles.row} role="row">
            <span className={styles.name} role="cell">
              {model.filename}
            </span>
            <span role="cell">
              <span className={styles.mobileLabel}>Format: </span>
              {model.format}
            </span>
            <span role="cell">
              <span className={styles.mobileLabel}>Size: </span>
              {formatBytes(model.size)}
            </span>
            <span role="cell">
              <span className={styles.mobileLabel}>Uploaded: </span>
              {new Date(model.createdAt).toLocaleDateString()}
            </span>
            <span className={styles.actions} role="cell">
              <Button variant="link" onClick={() => onCompress(model)}>
                Compress
              </Button>
              <Button variant="link" onClick={() => onConvert(model)}>
                Convert
              </Button>
              <Button variant="link" onClick={() => onDownload(model)}>
                Download
              </Button>
              <Button variant="link" onClick={() => setPendingDelete(model)}>
                Delete
              </Button>
            </span>
          </div>
        ))}
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Delete this model?"
          body={`"${pendingDelete.filename}" and every job run against it will be removed. This can't be undone.`}
          confirmLabel="Delete"
          onConfirm={() => {
            onDelete(pendingDelete)
            setPendingDelete(null)
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </>
  )
}
