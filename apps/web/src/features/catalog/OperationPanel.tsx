import { useEffect, useState } from 'react'
import type { ApiModel } from '../../api/types'
import { Panel } from '../../ui/Panel/Panel'
import { Tabs } from '../../ui/Tabs/Tabs'
import { JobRunner } from '../job/JobRunner'
import type { JobTab } from '../job/runButtonLabel'
import { MethodList } from './MethodList'
import { MethodParams } from './MethodParams'
import { SizeEstimate } from './SizeEstimate'
import { TechniqueTable } from './TechniqueTable'
import { useParamsState } from './paramsReducer'
import {
  getConverts,
  getMethodsForTechnique,
  getOperationById,
  getTechniques,
  type ParamValues,
} from './types'
import styles from './OperationPanel.module.css'

const OP_TABS: { id: JobTab; label: string }[] = [
  { id: 'compress', label: 'Compress' },
  { id: 'convert', label: 'Convert' },
]

export interface OperationPanelProps {
  model: ApiModel
  /** Prefills the method/convert-target selection and its param values — set when arriving from
   * the dashboard's "Re-run with edited settings" action. */
  initialOperationId?: string
  initialValues?: ParamValues
  /** Opens directly on Compress or Convert — set when arriving from a dashboard model row's
   * "Compress"/"Convert" action, independent of any `initialOperationId`. */
  initialTab?: JobTab
}

/** The "Method"/"Convert to" section (prototype's `#methods-h`): Compress/Convert tabs, the
 * technique comparison table on Compress, the method/convert-target list, schema-driven params,
 * a live size estimate, and the job runner for whichever operation is selected. */
export function OperationPanel({
  model,
  initialOperationId,
  initialValues,
  initialTab,
}: OperationPanelProps) {
  const initialOperation = initialOperationId ? getOperationById(initialOperationId) : undefined
  const [tab, setTab] = useState<JobTab>(
    initialOperation?.technique === 'convert' ? 'convert' : (initialTab ?? 'compress'),
  )
  const techniques = getTechniques()
  const [techniqueId, setTechniqueId] = useState(
    initialOperation && initialOperation.technique !== 'convert'
      ? initialOperation.technique
      : (techniques[0]?.id ?? ''),
  )
  const [selectedId, setSelectedId] = useState<string | null>(initialOperationId ?? null)
  const { valuesFor, ensureDefaults, setValue, seed } = useParamsState()

  useEffect(() => {
    if (!initialOperationId) return
    if (initialValues) seed(initialOperationId, initialValues)
    else ensureDefaults(initialOperationId, initialOperation?.params)
    // Seed once, from the values this panel was mounted with — not on every rerender.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const methods = getMethodsForTechnique(techniqueId)
  const converts = getConverts()
  const operations = tab === 'compress' ? methods : converts

  function selectOperation(id: string) {
    setSelectedId(id)
    const operation = getOperationById(id)
    ensureDefaults(id, operation?.params)
  }

  return (
    <Panel className={styles.panel}>
      <Tabs
        tabs={OP_TABS}
        activeId={tab}
        onChange={(id) => {
          setTab(id as JobTab)
          setSelectedId(null)
        }}
        aria-label="Operation"
      />

      {tab === 'compress' && (
        <div className={styles.techniques}>
          <TechniqueTable
            techniques={techniques}
            value={techniqueId}
            onChange={(id) => {
              setTechniqueId(id)
              setSelectedId(null)
            }}
          />
        </div>
      )}

      <h3 className={styles.heading}>{tab === 'compress' ? 'Method' : 'Convert to'}</h3>
      <MethodList
        operations={operations}
        model={model}
        selectedId={selectedId}
        onSelect={selectOperation}
        renderSelected={(operation) => {
          const values = valuesFor(operation.id, operation.params)
          return (
            <>
              <MethodParams
                operation={operation}
                model={model}
                values={values}
                onChange={(name, value) => setValue(operation.id, name, value)}
              />
              <SizeEstimate operationId={operation.id} model={model} values={values} />
              <JobRunner tab={tab} model={model} operation={operation} values={values} />
            </>
          )
        }}
      />
    </Panel>
  )
}
