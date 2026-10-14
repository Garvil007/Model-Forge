import type { ChangeEvent, DragEvent } from 'react'
import { Chip } from '../../ui/Chip/Chip'
import { DropZone } from '../../ui/FileInput/FileInput'
import { ACCEPTED_EXTENSIONS } from './detectFormat'
import { SAMPLE_LABELS, SAMPLE_MODELS } from './sampleModels'
import styles from './ModelDropzone.module.css'
import type { SampleKey } from './types'

export interface ModelDropzoneProps {
  onFile: (file: File) => void
  onSample: (sample: SampleKey) => void
  disabled?: boolean
}

const SAMPLE_KEYS = Object.keys(SAMPLE_MODELS) as SampleKey[]

/** The prototype's `.drop` + sample-model chips (lines 175-187): drag-over state, click to pick,
 * and the four sample buttons that skip straight to a detected model without a real upload. */
export function ModelDropzone({ onFile, onSample, disabled }: ModelDropzoneProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onFile(file)
    event.target.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLInputElement>) => {
    const file = event.dataTransfer?.files?.[0]
    if (file) onFile(file)
  }

  return (
    <div className={styles.dropzone}>
      <DropZone
        title="Drop a model file here"
        hint="or click to choose one"
        accept={ACCEPTED_EXTENSIONS}
        disabled={disabled}
        onChange={handleChange}
        onDrop={handleDrop}
      />
      <div className={styles.exts}>ONNX, TFLite, Keras, PyTorch, safetensors, YOLO, GGUF</div>
      <div className={styles.samples}>
        <p className={styles.samplesLabel}>Or try a sample</p>
        {SAMPLE_KEYS.map((key) => (
          <Chip key={key} disabled={disabled} onClick={() => onSample(key)}>
            {SAMPLE_LABELS[key]}
          </Chip>
        ))}
      </div>
    </div>
  )
}
