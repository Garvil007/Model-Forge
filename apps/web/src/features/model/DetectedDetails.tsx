import type { ChangeEvent } from 'react'
import { formatLabel } from '../catalog/formatLabels'
import { FileInput } from '../../ui/FileInput/FileInput'
import { Notice } from '../../ui/Notice/Notice'
import { Select } from '../../ui/Select/Select'
import { formatBytes, formatParams } from './format'
import styles from './DetectedDetails.module.css'
import type { DetectedModel } from './types'

const FAMILY_OPTIONS = [
  { value: 'vision', label: 'Vision / CNN' },
  { value: 'llm', label: 'Language model (LLM)' },
  { value: 'other', label: 'Other' },
]

export interface DetectedDetailsProps {
  model: DetectedModel
  onFamilyChange: (family: DetectedModel['family']) => void
  onValidationFile: (filename: string | null) => void
}

/** The "Your model" panel's post-detection content (prototype lines 529-546): the detected
 * properties list, the model-type selector (editable since detection is a guess), the optional
 * validation-data input, and the GGUF-is-already-quantized notice. */
export function DetectedDetails({ model, onFamilyChange, onValidationFile }: DetectedDetailsProps) {
  const handleValidationChange = (event: ChangeEvent<HTMLInputElement>) => {
    onValidationFile(event.target.files?.[0]?.name ?? null)
  }

  return (
    <div className={styles.info}>
      <dl className={styles.list}>
        <dt>File</dt>
        <dd>{model.filename}</dd>
        <dt>Format</dt>
        <dd>
          {formatLabel(model.format)}, {model.bits === 4.8 ? 'quantized' : `${model.bits}-bit`}
        </dd>
        <dt>Size</dt>
        <dd>
          {formatBytes(model.size)}, about {formatParams(model.params)} parameters
        </dd>
        {model.inputs && (
          <>
            <dt>Inputs</dt>
            <dd>{model.inputs}</dd>
          </>
        )}
      </dl>

      <Select
        label="Model type"
        help="Guessed from the file. Some methods, like GGUF and GPTQ, only apply to language models."
        options={FAMILY_OPTIONS}
        value={model.family}
        onChange={(event) => onFamilyChange(event.target.value as DetectedModel['family'])}
      />

      <FileInput
        label="Validation data (optional)"
        help="With labeled data, results show real accuracy before and after instead of an output comparison."
        accept=".zip,.csv,.jsonl,.parquet,.txt"
        onChange={handleValidationChange}
      />

      {model.format === 'gguf' && (
        <Notice variant="warning">
          GGUF files are already quantized. Re-quantizing them loses quality, so only conversion is
          offered.
        </Notice>
      )}
    </div>
  )
}
