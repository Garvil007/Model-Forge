import { describe, expect, it } from 'vitest'
import { JOB_POLL_INTERVAL_HIDDEN_MS, JOB_POLL_INTERVAL_MS, jobPollIntervalMs } from './hooks'

describe('jobPollIntervalMs', () => {
  it('polls every 2s while running and the tab is visible', () => {
    expect(jobPollIntervalMs('running', false)).toBe(JOB_POLL_INTERVAL_MS)
    expect(jobPollIntervalMs('queued', false)).toBe(JOB_POLL_INTERVAL_MS)
  })

  it('backs off to every 10s while the tab is hidden', () => {
    expect(jobPollIntervalMs('running', true)).toBe(JOB_POLL_INTERVAL_HIDDEN_MS)
    expect(jobPollIntervalMs('queued', true)).toBe(JOB_POLL_INTERVAL_HIDDEN_MS)
  })

  it('stops polling once the job reaches a terminal status, hidden or not', () => {
    for (const status of ['succeeded', 'failed', 'canceled'] as const) {
      expect(jobPollIntervalMs(status, false)).toBe(false)
      expect(jobPollIntervalMs(status, true)).toBe(false)
    }
  })

  it('stops polling when there is no job data yet', () => {
    expect(jobPollIntervalMs(undefined, false)).toBe(false)
  })
})
