import { cx } from '../cx'
import styles from './Spinner.module.css'

export interface SpinnerProps {
  size?: 'sm' | 'md'
  label?: string
}

export function Spinner({ size = 'md', label = 'Loading' }: SpinnerProps) {
  return <span role="status" aria-label={label} className={cx(styles.spinner, styles[size])} />
}
