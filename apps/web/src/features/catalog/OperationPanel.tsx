import { useState } from 'react'
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
import { getConverts, getMethodsForTechnique, getOperationById, getTechniques } from './types'
import styles from './OperationPanel.module.css'

const OP_TABS: { id: JobTab; label: string }[] = [
  { id: 'compress', label: 'Compress' },
  { id: 'convert', label: 'Convert' },
]

export interface OperationPanelProps {
  model: ApiModel
}

/** The "Method"/"Convert to" section (prototype's `#methods-h`): Compress/Convert tabs, the
 * technique comparison table on Compress, the method/convert-target list, schema-driven params,
 * a live size estimate, and the job runner for whichever operation is selected. */
export function OperationPanel({ model }: OperationPanelProps) {
  const [tab, setTab] = useState<JobTab>('compress')
  const techniques = getTechniques()
  const [techniqueId, setTechniqueId] = useState(techniques[0]?.id ?? '')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { valuesFor, ensureDefaults, setValue } = useParamsState()

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
