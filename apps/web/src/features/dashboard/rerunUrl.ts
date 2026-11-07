import type { ApiJob } from '../../api/types'

/** Builds the `/app` URL that prefills `ToolPage`/`OperationPanel` with a previous job's model,
 * operation and param values — the target of the job history table's "Re-run" action. */
export function buildRerunUrl(job: ApiJob): string {
  const params = new URLSearchParams({ modelId: job.modelId, operationId: job.operationId })
  if (Object.keys(job.values).length > 0) {
    params.set('values', JSON.stringify(job.values))
  }
  return `/app?${params.toString()}`
}
