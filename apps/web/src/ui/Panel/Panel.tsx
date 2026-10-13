import type { HTMLAttributes } from 'react'
import { cx } from '../cx'
import styles from './Panel.module.css'

export function Panel({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <section className={cx(styles.panel, className)} {...rest} />
}
