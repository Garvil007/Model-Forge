import { cx } from '../cx'
import styles from './Skeleton.module.css'

export interface SkeletonProps {
  width?: string | number
  height?: string | number
  className?: string
}

export function Skeleton({ width = '100%', height = '1em', className }: SkeletonProps) {
  return (
    <div aria-hidden="true" className={cx(styles.skeleton, className)} style={{ width, height }} />
  )
}
