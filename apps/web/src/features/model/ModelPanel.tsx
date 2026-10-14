import { useEffect, useState } from 'react'
import { Panel } from '../../ui/Panel/Panel'
import { Spinner } from '../../ui/Spinner/Spinner'
import { Notice } from '../../ui/Notice/Notice'
import { Button } from '../../ui/Button/Button'
import { Tabs } from '../../ui/Tabs/Tabs'
import { detectModel } from './detectFormat'
import { DetectedDetails } from './DetectedDetails'
import { HfImportForm } from './HfImportForm'
import { ModelDropzone } from './ModelDropzone'
import { SAMPLE_MODELS } from './sampleModels'
import styles from './ModelPanel.module.css'
import type { DetectedModel, SampleKey } from './types'
import { UploadProgress } from './UploadProgress'
import { useFileUpload } from './useFileUpload'

export type ReadyModel = DetectedModel & { id?: string }

export interface ModelPanelProps {
  onModelReady?: (model: ReadyModel) => void
}

const TABS = [
  { id: 'upload', label: 'Upload' },
  { id: 'huggingface', label: 'Hugging Face' },
]

const CHECK_DELAY_MS = 400

/** "Your model" panel (prototype `#model-h` section): pick a file or a sample or import from
 * Hugging Face, see a brief "checking" state, then the detected details — with a real multipart
 * upload running in the background for a picked file. */
export function ModelPanel({ onModelReady }: ModelPanelProps) {
  const [activeTab, setActiveTab] = useState('upload')
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState<string | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [detected, setDetected] = useState<DetectedModel | null>(null)
  const upload = useFileUpload()

  useEffect(() => {
    if (upload.state.status !== 'uploading' && upload.state.status !== 'paused') return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [upload.state.status])

  const runUpload = (file: File, model: DetectedModel) => {
    upload
      .start(file, model)
      .then((apiModel) => onModelReady?.({ ...model, id: apiModel.id }))
      .catch(() => {
        // Terminal failure is already reflected in upload.state.error; nothing further to do.
      })
  }

  const checkFile = (file: File) => {
    setPendingFile(file)
    setChecking(true)
    setCheckError(null)
    setDetected(null)
    upload.reset()
    window.setTimeout(() => {
      setChecking(false)
      try {
        const model = detectModel(file)
        setDetected(model)
        runUpload(file, model)
      } catch (error) {
        setCheckError(error instanceof Error ? error.message : 'Could not read that file.')
      }
    }, CHECK_DELAY_MS)
  }

  const retry = () => {
    if (pendingFile) checkFile(pendingFile)
  }

  const pickSample = (key: SampleKey) => {
    const model = SAMPLE_MODELS[key]
    setPendingFile(null)
    setChecking(false)
    setCheckError(null)
    upload.reset()
    setDetected(model)
    onModelReady?.(model)
  }

  const handleFamilyChange = (family: DetectedModel['family']) => {
    if (!detected) return
    setDetected({ ...detected, family })
  }

  const dropzoneBusy =
    checking || upload.state.status === 'uploading' || upload.state.status === 'completing'

  return (
    <Panel aria-labelledby="model-panel-h" className={styles.panel}>
      <h2 id="model-panel-h" className={styles.heading}>
        Your model
      </h2>
      <Tabs tabs={TABS} activeId={activeTab} onChange={setActiveTab} aria-label="Model source" />

      {activeTab === 'upload' ? (
        <ModelDropzone onFile={checkFile} onSample={pickSample} disabled={dropzoneBusy} />
      ) : (
        <HfImportForm onImported={(model) => onModelReady?.(model)} />
      )}

      {checking && (
        <div className={styles.checking} role="status">
          <Spinner size="sm" label="Checking model" />
          Checking your model…
        </div>
      )}

      {checkError && (
        <Notice variant="error">
          {checkError}
          <div className={styles.retryRow}>
            <Button variant="link" onClick={retry}>
              Try again
            </Button>
          </div>
        </Notice>
      )}

      {detected && (
        <DetectedDetails
          model={detected}
          onFamilyChange={handleFamilyChange}
          onValidationFile={() => {}}
        />
      )}

      {(upload.state.status === 'uploading' ||
        upload.state.status === 'paused' ||
        upload.state.status === 'completing') && (
        <UploadProgress
          state={upload.state}
          onPause={upload.pause}
          onResume={upload.resume}
          onCancel={upload.cancel}
        />
      )}

      {upload.state.status === 'error' && upload.state.error && (
        <Notice variant="error">{upload.state.error}</Notice>
      )}
    </Panel>
  )
}
