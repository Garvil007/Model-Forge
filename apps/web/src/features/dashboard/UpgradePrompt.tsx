import { useNavigate } from 'react-router-dom'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import styles from './UpgradePrompt.module.css'

export interface UpgradePromptProps {
  message: string
}

/** Inline, dismiss-by-navigating nudge toward `/pricing` — never a modal. Shown where a
 * plan limit has been hit or is close to it (quota_exceeded job errors, near-full usage
 * on the dashboard), so upgrading is always one click away but never blocks the page. */
export function UpgradePrompt({ message }: UpgradePromptProps) {
  const navigate = useNavigate()
  return (
    <Notice variant="warning" className={styles.wrap}>
      <span>{message}</span>
      <Button variant="link" onClick={() => navigate('/pricing')}>
        Upgrade to Pro
      </Button>
    </Notice>
  )
}
