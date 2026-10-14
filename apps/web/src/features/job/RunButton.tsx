import { Button } from '../../ui/Button/Button'
import styles from './RunButton.module.css'

export interface RunButtonProps {
  label: string
  disabled: boolean
  running: boolean
  onClick: () => void
}

/** The run button itself — `label`/`disabled` come from `runButtonState()`; `running` only
 * controls the spinner, kept separate so a missing-param disable doesn't look like a spinner. */
export function RunButton({ label, disabled, running, onClick }: RunButtonProps) {
  return (
    <Button className={styles.button} disabled={disabled} loading={running} onClick={onClick}>
      {label}
    </Button>
  )
}
