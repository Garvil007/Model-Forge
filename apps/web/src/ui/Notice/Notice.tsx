import type { HTMLAttributes } from 'react'
import { cx } from '../cx'
import styles from './Notice.module.css'

export type NoticeVariant = 'info' | 'warning' | 'error'

export interface NoticeProps extends HTMLAttributes<HTMLDivElement> {
  variant?: NoticeVariant
}

export function Notice({ variant = 'info', className, ...rest }: NoticeProps) {
  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={cx(styles.notice, styles[variant], className)}
      {...rest}
    />
  )
}
