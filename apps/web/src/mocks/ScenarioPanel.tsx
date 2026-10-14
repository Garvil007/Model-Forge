import { useState } from 'react'
import { Button } from '../ui/Button/Button'
import { NumberInput } from '../ui/NumberInput/NumberInput'
import { Panel } from '../ui/Panel/Panel'
import { Select } from '../ui/Select/Select'
import { Toggle } from '../ui/Toggle/Toggle'
import styles from './ScenarioPanel.module.css'
import { DEFAULT_SCENARIOS, getScenarios, resetScenarios, setScenarios } from './scenarios'

const JOB_ERROR_OPTIONS = [
  { value: 'none', label: 'None (job succeeds)' },
  { value: 'out_of_memory', label: 'Out of memory' },
  { value: 'unsupported_operator', label: 'Unsupported operator' },
  { value: 'bad_calibration_data', label: 'Bad calibration data' },
  { value: 'gated_model', label: 'Gated model' },
  { value: 'spot_interrupted', label: 'Spot interruption' },
]

/** Dev-only panel for exercising the mock backend's failure modes while building the UI against
 * it — rendered only when `VITE_USE_MOCKS=true` (see `App.tsx`). Never shipped to a real backend. */
export function ScenarioPanel() {
  const [scenarios, setLocalScenarios] = useState(getScenarios())

  const update = (patch: Partial<typeof scenarios>) => {
    setScenarios(patch)
    setLocalScenarios(getScenarios())
  }

  return (
    <Panel className={styles.panel}>
      <h2 className={styles.heading}>Mock backend scenarios</h2>
      <Toggle
        label="Slow network"
        checked={scenarios.slowNetwork}
        onChange={(e) => update({ slowNetwork: e.target.checked })}
      />
      <NumberInput
        label="Fail upload part number (0 = off)"
        min={0}
        value={scenarios.uploadFailPart}
        onChange={(e) => update({ uploadFailPart: Number(e.target.value) || 0 })}
      />
      <Select
        label="Job error"
        options={JOB_ERROR_OPTIONS}
        value={scenarios.jobErrorKind}
        onChange={(e) => update({ jobErrorKind: e.target.value as typeof scenarios.jobErrorKind })}
      />
      <Toggle
        label="Quota exceeded"
        checked={scenarios.quotaExceeded}
        onChange={(e) => update({ quotaExceeded: e.target.checked })}
      />
      <Toggle
        label="Expired session"
        checked={scenarios.expiredSession}
        onChange={(e) => update({ expiredSession: e.target.checked })}
      />
      <Button
        variant="secondary"
        onClick={() => {
          resetScenarios()
          setLocalScenarios(getScenarios())
        }}
      >
        Reset
      </Button>
      <small className={styles.hint}>Defaults: {JSON.stringify(DEFAULT_SCENARIOS)}</small>
    </Panel>
  )
}
