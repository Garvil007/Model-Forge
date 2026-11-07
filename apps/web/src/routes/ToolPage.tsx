import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useModel } from '../api/hooks'
import { Notice } from '../ui/Notice/Notice'
import { Spinner } from '../ui/Spinner/Spinner'
import { OperationPanel } from '../features/catalog/OperationPanel'
import type { ParamValues } from '../features/catalog/types'
import { ModelPanel, type ReadyModel } from '../features/model/ModelPanel'
import { ScenarioPanel } from '../mocks/ScenarioPanel'
import styles from './LandingPage.module.css'

const useMocks = import.meta.env.VITE_USE_MOCKS === 'true'

function parseRerunValues(raw: string | null): ParamValues | undefined {
  if (!raw) return undefined
  try {
    return JSON.parse(raw) as ParamValues
  } catch {
    return undefined
  }
}

export function ToolPage() {
  const [readyModel, setReadyModel] = useState<ReadyModel | null>(null)
  const [searchParams] = useSearchParams()
  const rerunModelId = searchParams.get('modelId')
  const rerunOperationId = searchParams.get('operationId') ?? undefined
  const rerunValues = parseRerunValues(searchParams.get('values'))
  const initialTab = searchParams.get('tab') === 'convert' ? 'convert' : undefined

  const { data: apiModel } = useModel(rerunModelId ?? readyModel?.id)

  return (
    <div className={styles.toolWrap}>
      <h1 className={styles.toolTitle}>ModelForge</h1>
      <p className={styles.toolSubtitle}>
        Upload a model, compress or convert it, and download the result.
      </p>
      {rerunModelId ? (
        apiModel ? (
          <Notice variant="info">
            Re-running against {apiModel.filename} — edit the settings below before running.
          </Notice>
        ) : (
          <Spinner label="Loading model" />
        )
      ) : (
        <>
          <ModelPanel onModelReady={setReadyModel} />
          {readyModel && !readyModel.id && (
            <Notice variant="info">
              Sample models are for browsing methods only — upload a file or import from Hugging
              Face to run a job.
            </Notice>
          )}
        </>
      )}
      {apiModel && (
        <OperationPanel
          model={apiModel}
          initialOperationId={rerunOperationId}
          initialValues={rerunValues}
          initialTab={initialTab}
        />
      )}
      {useMocks && <ScenarioPanel />}
    </div>
  )
}
