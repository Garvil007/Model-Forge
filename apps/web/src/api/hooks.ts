import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query'
import type { Catalog } from '../features/catalog/types'
import { apiClient } from './client'
import type { ApiJob, ApiModel, CreateJobRequest, ImportHfRequest } from './types'

export const queryKeys = {
  catalog: ['catalog'] as const,
  models: ['models'] as const,
  model: (id: string) => ['models', id] as const,
  jobs: ['jobs'] as const,
  job: (id: string) => ['jobs', id] as const,
}

export function useCatalog() {
  return useQuery({
    queryKey: queryKeys.catalog,
    queryFn: ({ signal }) => apiClient.get<Catalog>('/catalog', { signal }),
    staleTime: Infinity,
  })
}

export function useModels() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: ({ signal }) => apiClient.get<ApiModel[]>('/models', { signal }),
  })
}

const MODEL_POLL_INTERVAL_MS = 2000

/** Polls while the server is still working out the model's real format (`importing` for a
 * Hugging Face download, `checking` for the detect_format worker job) and stops once it
 * reaches `ready`/`failed` — or immediately, for the mock, which never sets `status` at all. */
export function useModel(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.model(id ?? ''),
    queryFn: ({ signal }) => apiClient.get<ApiModel>(`/models/${id}`, { signal }),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'importing' || status === 'checking' ? MODEL_POLL_INTERVAL_MS : false
    },
  })
}

export function useImportHf() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ImportHfRequest) => apiClient.post<ApiModel>('/models/import-hf', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.models }),
  })
}

export const JOB_POLL_INTERVAL_MS = 2000
export const JOB_POLL_INTERVAL_HIDDEN_MS = 10000

/** Pure polling-interval decision, pulled out of `refetchInterval` so it's testable without
 * waiting on real timers: 2s while visible, 10s backoff while hidden, off once terminal. */
export function jobPollIntervalMs(
  status: ApiJob['status'] | undefined,
  hidden: boolean,
): number | false {
  if (status !== 'running' && status !== 'queued') return false
  return hidden ? JOB_POLL_INTERVAL_HIDDEN_MS : JOB_POLL_INTERVAL_MS
}

/** Jobs are still progressing while `running`/`queued`; `refetchInterval` keeps polling until the
 * job reaches a terminal status, matching the prototype's stage-by-stage progress view.
 * `refetchIntervalInBackground` is required for the hidden-tab backoff to keep running rather
 * than pausing outright while hidden. */
export function useJob(id: string | undefined, options?: Pick<UseQueryOptions<ApiJob>, 'enabled'>) {
  return useQuery({
    queryKey: queryKeys.job(id ?? ''),
    queryFn: ({ signal }) => apiClient.get<ApiJob>(`/jobs/${id}`, { signal }),
    enabled: Boolean(id) && (options?.enabled ?? true),
    refetchIntervalInBackground: true,
    refetchInterval: (query) =>
      jobPollIntervalMs(
        query.state.data?.status,
        typeof document !== 'undefined' && document.hidden,
      ),
  })
}

export function useCreateJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateJobRequest) => apiClient.post<ApiJob>('/jobs', body),
    onSuccess: (job) => {
      queryClient.setQueryData(queryKeys.job(job.id), job)
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs })
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.post<ApiJob>(`/jobs/${id}/cancel`),
    onSuccess: (job) => queryClient.setQueryData(queryKeys.job(job.id), job),
  })
}
