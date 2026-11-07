import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDeleteModel, useDownloadModel, useJobsHistory, useModels, useUsage } from '../api/hooks'
import type {
  ApiJob,
  ApiModel,
  ApiUsage,
  JobHistoryFilters as JobHistoryFiltersValue,
} from '../api/types'
import { CompareView } from '../features/dashboard/CompareView'
import { JobHistoryFilters } from '../features/dashboard/JobHistoryFilters'
import { JobHistoryTable } from '../features/dashboard/JobHistoryTable'
import { ModelsTable } from '../features/dashboard/ModelsTable'
import { buildRerunUrl } from '../features/dashboard/rerunUrl'
import { StorageUsage } from '../features/dashboard/StorageUsage'
import { UpgradePrompt } from '../features/dashboard/UpgradePrompt'
import { Notice } from '../ui/Notice/Notice'
import { Panel } from '../ui/Panel/Panel'
import { Tabs } from '../ui/Tabs/Tabs'
import styles from './DashboardPage.module.css'

type DashboardTab = 'models' | 'history' | 'compare'

const TABS = [
  { id: 'models', label: 'My models' },
  { id: 'history', label: 'Job history' },
  { id: 'compare', label: 'Compare' },
]

const NEAR_LIMIT_THRESHOLD = 0.8

function isNearLimit(used: number, limit: number): boolean {
  return limit > 0 && used / limit >= NEAR_LIMIT_THRESHOLD
}

function isNearAnyLimit(usage: ApiUsage): boolean {
  return (
    isNearLimit(usage.cpuSecondsUsed, usage.cpuSecondsLimit) ||
    isNearLimit(usage.gpuSecondsUsed, usage.gpuSecondsLimit) ||
    isNearLimit(usage.storageBytesUsed, usage.storageBytesLimit)
  )
}

export function DashboardPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<DashboardTab>('models')

  const { data: models = [], isLoading: modelsLoading, isError: modelsError } = useModels()
  const deleteModel = useDeleteModel()
  const downloadModel = useDownloadModel()
  const { data: usage, isLoading: usageLoading, isError: usageError } = useUsage()

  const [filters, setFilters] = useState<JobHistoryFiltersValue>({})
  const jobsHistory = useJobsHistory(filters)
  const jobs = jobsHistory.data?.pages.flatMap((page) => page.items) ?? []

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  function toggleSelect(job: ApiJob) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(job.id)) next.delete(job.id)
      else next.add(job.id)
      return next
    })
  }
  const selectedJobs = jobs.filter((job) => selectedIds.has(job.id))
  const compareModel = selectedJobs[0] && models.find((m) => m.id === selectedJobs[0].modelId)

  function goToTool(model: ApiModel, opTab: 'compress' | 'convert') {
    navigate(`/app?modelId=${model.id}&tab=${opTab}`)
  }

  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Dashboard</h1>

      <Panel className={styles.storagePanel}>
        <StorageUsage
          usedBytes={usage?.storageBytesUsed ?? 0}
          limitBytes={usage?.storageBytesLimit ?? 0}
          retentionDays={usage?.retentionDays ?? 0}
          isLoading={usageLoading}
          isError={usageError}
        />
      </Panel>

      {usage && usage.plan === 'free' && isNearAnyLimit(usage) && (
        <UpgradePrompt message="You're close to a Free plan limit — upgrade for more quota, GPU methods and longer retention." />
      )}

      <Tabs
        tabs={TABS}
        activeId={tab}
        onChange={(id) => setTab(id as DashboardTab)}
        aria-label="Dashboard section"
      />

      <Panel className={styles.sectionPanel}>
        {tab === 'models' && (
          <ModelsTable
            models={models}
            isLoading={modelsLoading}
            isError={modelsError}
            onCompress={(model) => goToTool(model, 'compress')}
            onConvert={(model) => goToTool(model, 'convert')}
            onDownload={(model) =>
              downloadModel.mutate(model.id, {
                onSuccess: ({ url }) => window.open(url, '_blank', 'noopener'),
              })
            }
            onDelete={(model) => deleteModel.mutate(model.id)}
          />
        )}

        {tab === 'history' && (
          <>
            <JobHistoryFilters value={filters} onChange={setFilters} />
            <JobHistoryTable
              jobs={jobs}
              models={models}
              isLoading={jobsHistory.isLoading}
              isError={jobsHistory.isError}
              hasNextPage={jobsHistory.hasNextPage}
              isFetchingNextPage={jobsHistory.isFetchingNextPage}
              onLoadMore={() => jobsHistory.fetchNextPage()}
              onRerun={(job) => navigate(buildRerunUrl(job))}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
            />
          </>
        )}

        {tab === 'compare' &&
          (compareModel ? (
            <CompareView model={compareModel} jobs={selectedJobs} />
          ) : (
            <Notice variant="info">
              Pick at least two succeeded jobs for the same model from the Job history tab's compare
              checkboxes.
            </Notice>
          ))}
      </Panel>
    </div>
  )
}
