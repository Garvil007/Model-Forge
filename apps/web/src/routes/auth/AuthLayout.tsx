import type { FormEvent, ReactNode } from 'react'
import { Panel } from '../../ui/Panel/Panel'
import styles from './AuthLayout.module.css'

export interface AuthLayoutProps {
  title: string
  subtitle?: string
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  children: ReactNode
  footer?: ReactNode
}

export function AuthLayout({ title, subtitle, onSubmit, children, footer }: AuthLayoutProps) {
  return (
    <div className={styles.wrap}>
      <Panel>
        <h1 className={styles.title}>{title}</h1>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        <form className={styles.form} onSubmit={onSubmit} noValidate>
          {children}
        </form>
        {footer && <div className={styles.footerLink}>{footer}</div>}
      </Panel>
    </div>
  )
}
