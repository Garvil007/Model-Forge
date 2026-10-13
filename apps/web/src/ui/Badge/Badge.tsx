import { cx } from '../cx'
import styles from './Badge.module.css'

export type BadgeVariant = 'lossless' | 'near-lossless' | 'lossy'

const LABEL: Record<BadgeVariant, string> = {
  lossless: 'No accuracy change',
  'near-lossless': 'Tiny accuracy change',
  lossy: 'Some accuracy loss',
}

export interface BadgeProps {
  variant: BadgeVariant
  className?: string
}

export function Badge({ variant, className }: BadgeProps) {
  return <span className={cx(styles.badge, styles[variant], className)}>{LABEL[variant]}</span>
}
