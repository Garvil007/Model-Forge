import { useEffect } from 'react'
import { Button } from '../../ui/Button/Button'
import styles from './ConfirmDialog.module.css'

export interface ConfirmDialogProps {
  title: string
  body: string
  /** Extra "Estimated time: X · Estimated cost: Y" style facts, shown above the actions. */
  meta?: string[]
  confirmLabel: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

/** Generic confirmation modal — used both for the expensive-job confirmation (time + cost in
 * `meta`) and for the cancel-running-job confirmation. Escape and the backdrop both cancel. */
export function ConfirmDialog({
  title,
  body,
  meta,
  confirmLabel,
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onCancel])

  return (
    <div
      className={styles.overlay}
      onClick={(event) => {
        if (event.target === event.currentTarget) onCancel()
      }}
    >
      <div
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <h2 id="confirm-title" className={styles.title}>
          {title}
        </h2>
        <p className={styles.body}>{body}</p>
        {meta && meta.length > 0 && (
          <div className={styles.meta}>
            {meta.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        )}
        <div className={styles.actions}>
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button autoFocus onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
