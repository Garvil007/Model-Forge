import { describe, expect, it } from 'vitest'
import type { ApiJob } from '../../api/types'
import { buildRerunUrl } from './rerunUrl'

function job(values: Record<string, unknown>): ApiJob {
  return {
    id: 'job_1',
    modelId: 'model_1',
    operationId: 'q_int8_static',
    values,
    status: 'succeeded',
    stages: [],
    createdAt: '2026-10-21T10:00:00.000Z',
    result: null,
    error: null,
    cost: 0.03,
  }
}

describe('buildRerunUrl', () => {
  it('includes modelId and operationId', () => {
    const url = buildRerunUrl(job({}))
    expect(url).toBe('/app?modelId=model_1&operationId=q_int8_static')
  })

  it('includes the job values as JSON when present', () => {
    const url = buildRerunUrl(job({ bits: 8 }))
    const params = new URLSearchParams(url.split('?')[1])
    expect(JSON.parse(params.get('values')!)).toEqual({ bits: 8 })
  })
})
