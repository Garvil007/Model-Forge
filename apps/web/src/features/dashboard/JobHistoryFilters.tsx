import type { JobHistoryFilters as JobHistoryFiltersValue, JobStatus } from '../../api/types'
import { Select } from '../../ui/Select/Select'
import { TextInput } from '../../ui/TextInput/TextInput'
import { CATALOG } from '../catalog/types'
import styles from './JobHistoryFilters.module.css'

const STATUS_OPTIONS: { value: '' | JobStatus; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'canceled', label: 'Canceled' },
]

export interface JobHistoryFiltersProps {
  value: JobHistoryFiltersValue
  onChange: (value: JobHistoryFiltersValue) => void
}

/** Status / technique / date-range filters for the job history table — each change replaces
 * the whole filters object so the parent can reset pagination in one place. */
export function JobHistoryFilters({ value, onChange }: JobHistoryFiltersProps) {
  const techniqueOptions = [
    { value: '', label: 'All techniques' },
    ...CATALOG.operations.map((op) => ({ value: op.id, label: op.label })),
  ]

  return (
    <div className={styles.filters}>
      <Select
        label="Status"
        options={STATUS_OPTIONS}
        value={value.status ?? ''}
        onChange={(e) =>
          onChange({
            ...value,
            status: (e.target.value || undefined) as JobStatus | undefined,
          })
        }
      />
      <Select
        label="Technique"
        options={techniqueOptions}
        value={value.operationId ?? ''}
        onChange={(e) => onChange({ ...value, operationId: e.target.value || undefined })}
      />
      <TextInput
        label="From"
        type="date"
        value={value.dateFrom ?? ''}
        onChange={(e) => onChange({ ...value, dateFrom: e.target.value || undefined })}
      />
      <TextInput
        label="To"
        type="date"
        value={value.dateTo ?? ''}
        onChange={(e) => onChange({ ...value, dateTo: e.target.value || undefined })}
      />
    </div>
  )
}
