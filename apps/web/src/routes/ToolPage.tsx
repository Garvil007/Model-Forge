import { useState } from 'react'
import { useModel } from '../api/hooks'
import { Notice } from '../ui/Notice/Notice'
import { OperationPanel } from '../features/catalog/OperationPanel'
import { ModelPanel, type ReadyModel } from '../features/model/ModelPanel'
import { ScenarioPanel } from '../mocks/ScenarioPanel'
import styles from './LandingPage.module.css'

const useMocks = import.meta.env.VITE_USE_MOCKS === 'true'

export function ToolPage() {
  const [readyModel, setReadyModel] = useState<ReadyModel | null>(null)
  const { data: apiModel } = useModel(readyModel?.id)

  return (
    <div className={styles.toolWrap}>
      <h1 className={styles.toolTitle}>ModelForge</h1>
      <p className={styles.toolSubtitle}>
        Upload a model, compress or convert it, and download the result.
      </p>
      <ModelPanel onModelReady={setReadyModel} />
      {readyModel && !readyModel.id && (
        <Notice variant="info">
          Sample models are for browsing methods only — upload a file or import from Hugging Face
          to run a job.
        </Notice>
      )}
      {apiModel && <OperationPanel model={apiModel} />}
      {useMocks && <ScenarioPanel />}
    </div>
  )
}
