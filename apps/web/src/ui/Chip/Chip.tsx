import type { ButtonHTMLAttributes } from 'react'
import { cx } from '../cx'
import styles from './Chip.module.css'

export function Chip({ className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={cx(styles.chip, className)} {...rest} />
}
