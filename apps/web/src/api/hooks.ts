import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'
import type { Catalog } from '../features/catalog/types'
import { apiClient } from './client'
import type {
  ApiBillingPlan,
  ApiJob,
  ApiModel,
  ApiSettings,
  ApiUsage,
  BillingRedirect,
  CreateJobRequest,
  ImportHfRequest,
  JobHistoryFilters,
  NotificationSettings,
  PaginatedJobs,
} from './types'

export const queryKeys = {
  catalog: ['catalog'] as const,
  models: ['models'] as const,
  model: (id: string) => ['models', id] as const,
  jobs: ['jobs'] as const,
  job: (id: string) => ['jobs', id] as const,
  jobsHistory: (filters: JobHistoryFilters) => ['jobs', 'history', filters] as const,
  usage: ['usage'] as const,
  settings: ['settings'] as const,
  billingPlans: ['billing', 'plans'] as const,
}

/** Free/Pro display data for `/pricing`. */
export function useBillingPlans() {
  return useQuery({
    queryKey: queryKeys.billingPlans,
    queryFn: ({ signal }) => apiClient.get<ApiBillingPlan[]>('/billing/plans', { signal }),
    staleTime: Infinity,
  })
}

/** Stripe Checkout for the Pro subscription — caller redirects the browser to `url`. */
export function useCreateCheckoutSession() {
  return useMutation({
    mutationFn: () => apiClient.post<BillingRedirect>('/billing/checkout-session'),
  })
}

/** Stripe Customer Portal (manage payment method, cancel) — caller redirects to `url`. */
export function useCreatePortalSession() {
  return useMutation({
    mutationFn: () => apiClient.post<BillingRedirect>('/billing/portal-session'),
  })
}

export function useCatalog() {
  return useQuery({
    queryKey: queryKeys.catalog,
    queryFn: ({ signal }) => apiClient.get<Catalog>('/catalog', { signal }),
    staleTime: Infinity,
  })
}

/** Remaining monthly CPU/GPU quota, for the dashboard's quota display. */
export function useUsage() {
  return useQuery({
    queryKey: queryKeys.usage,
    queryFn: ({ signal }) => apiClient.get<ApiUsage>('/usage', { signal }),
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

export function useDeleteModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`/models/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.models }),
  })
}

export function useDownloadModel() {
  return useMutation({
    mutationFn: (id: string) => apiClient.get<{ url: string }>(`/models/${id}/download`),
  })
}

export function useDownloadJobResult() {
  return useMutation({
    mutationFn: (id: string) => apiClient.get<{ url: string }>(`/jobs/${id}/download`),
  })
}

function jobsHistoryQueryString(filters: JobHistoryFilters, cursor: string | undefined): string {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.operationId) params.set('operationId', filters.operationId)
  if (filters.dateFrom) params.set('dateFrom', filters.dateFrom)
  if (filters.dateTo) params.set('dateTo', filters.dateTo)
  if (cursor) params.set('cursor', cursor)
  const query = params.toString()
  return query ? `?${query}` : ''
}

/** Job history, newest first, paged via the DynamoDB cursor the API hands back as
 * `nextCursor` — `fetchNextPage` asks for the next page with that cursor attached. */
export function useJobsHistory(filters: JobHistoryFilters) {
  return useInfiniteQuery({
    queryKey: queryKeys.jobsHistory(filters),
    queryFn: ({ pageParam, signal }) =>
      apiClient.get<PaginatedJobs>(`/jobs${jobsHistoryQueryString(filters, pageParam)}`, {
        signal,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
  })
}

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: ({ signal }) => apiClient.get<ApiSettings>('/settings', { signal }),
  })
}

export function useUpdateNotifications() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (notifications: NotificationSettings) =>
      apiClient.put<ApiSettings>('/settings/notifications', { notifications }),
    onSuccess: (settings) => queryClient.setQueryData(queryKeys.settings, settings),
  })
}

export function useSetHfToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string) => apiClient.put<ApiSettings>('/settings/hf-token', { token }),
    onSuccess: (settings) => queryClient.setQueryData(queryKeys.settings, settings),
  })
}

export function useClearHfToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.delete<ApiSettings>('/settings/hf-token'),
    onSuccess: (settings) => queryClient.setQueryData(queryKeys.settings, settings),
  })
}

export function useDeleteAccount() {
  return useMutation({
    mutationFn: () => apiClient.delete<void>('/account', { confirm: 'DELETE' }),
  })
}
