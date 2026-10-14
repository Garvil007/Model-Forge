import { useEffect, useState } from 'react'
import { cx } from '../../ui/cx'
import { Button } from '../../ui/Button/Button'
import { formatBytes } from './resultFormulas'
import styles from './ResultPanel.module.css'

export interface ResultMetric {
  label: string
  value: string
}

export interface ResultPanelProps {
  headline: string
  operationLabel: string
  speedNote: string | null
  beforeBytes: number
  afterBytes: number
  beforeWidthPercent: number
  afterWidthPercent: number
  metrics: ResultMetric[]
  measuredOnValidation: boolean
  downloadName: string
  onDownload: () => void
  onTryOtherSettings: () => void
}

/** The finished-job result — headline percentage, animated before/after ruler (the animation is
 * a plain CSS width transition, disabled under `prefers-reduced-motion` in the stylesheet), the
 * metrics table, a speed note, download, and "Try other settings". Port of `showResult()`. */
export function ResultPanel({
  headline,
  operationLabel,
  speedNote,
  beforeBytes,
  afterBytes,
  beforeWidthPercent,
  afterWidthPercent,
  metrics,
  measuredOnValidation,
  downloadName,
  onDownload,
  onTryOtherSettings,
}: ResultPanelProps) {
  const [animatedIn, setAnimatedIn] = useState(false)
  useEffect(() => {
    const frame = requestAnimationFrame(() => setAnimatedIn(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div className={styles.panel}>
      <div className={styles.headline}>{headline}</div>
      <div className={styles.sub}>
        {operationLabel}
        {speedNote ? `, ${speedNote}` : ''}
      </div>

      <div className={styles.ruler}>
        <div className={styles.row}>
          <span>Before</span>
          <span className={styles.track}>
            <span className={styles.fill} style={{ width: `${beforeWidthPercent}%` }} />
          </span>
          <span>{formatBytes(beforeBytes)}</span>
        </div>
        <div className={cx(styles.row, styles.after)}>
          <span>After</span>
          <span className={styles.track}>
            <span
              className={styles.fill}
              style={{ width: `${animatedIn ? afterWidthPercent : 0}%` }}
            />
          </span>
          <span>{formatBytes(afterBytes)}</span>
        </div>
      </div>

      <table className={styles.metrics}>
        <tbody>
          {metrics.map((metric) => (
            <tr key={metric.label}>
              <td>{metric.label}</td>
              <td>{metric.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <small className={styles.note}>
        {measuredOnValidation
          ? 'Measured on the validation set.'
          : 'Compared on random inputs. Add validation data to see real accuracy.'}
      </small>

      <div className={styles.actions}>
        <Button variant="link" onClick={onDownload}>
          Download {downloadName}
        </Button>
        <Button variant="link" onClick={onTryOtherSettings}>
          Try other settings
        </Button>
      </div>
    </div>
  )
}
