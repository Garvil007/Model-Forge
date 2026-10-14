import { describe, expect, it } from 'vitest'
import { paramsReducer } from './paramsReducer'
import type { ParamsState } from './paramsReducer'
import type { Param } from './types'

const PARAMS: Param[] = [
  { name: 'sparsity', label: 'Sparsity', type: 'range', default: 50 },
  { name: 'finetune', label: 'Fine-tune', type: 'check', default: true },
]

describe('paramsReducer', () => {
  it('fills in defaults for an operation seen for the first time', () => {
    const state = paramsReducer(
      {},
      { type: 'ensure-defaults', operationId: 'p_magnitude', params: PARAMS },
    )
    expect(state.p_magnitude).toEqual({ sparsity: 50, finetune: true })
  })

  it('does not clobber existing values when defaults are re-applied', () => {
    const seeded: ParamsState = { p_magnitude: { sparsity: 80, finetune: false } }
    const state = paramsReducer(seeded, {
      type: 'ensure-defaults',
      operationId: 'p_magnitude',
      params: PARAMS,
    })
    expect(state.p_magnitude).toEqual({ sparsity: 80, finetune: false })
  })

  it('sets a single value without touching other operations', () => {
    const seeded: ParamsState = { q_fp16: {}, p_magnitude: { sparsity: 50 } }
    const state = paramsReducer(seeded, {
      type: 'set-value',
      operationId: 'p_magnitude',
      name: 'sparsity',
      value: 70,
    })
    expect(state.p_magnitude).toEqual({ sparsity: 70 })
    expect(state.q_fp16).toEqual({})
  })

  it('preserves typed values across a method switch and back', () => {
    let state: ParamsState = {}
    state = paramsReducer(state, {
      type: 'ensure-defaults',
      operationId: 'p_magnitude',
      params: PARAMS,
    })
    state = paramsReducer(state, {
      type: 'set-value',
      operationId: 'p_magnitude',
      name: 'sparsity',
      value: 90,
    })
    // switch to another method
    state = paramsReducer(state, { type: 'ensure-defaults', operationId: 'q_fp16', params: [] })
    // switch back
    state = paramsReducer(state, {
      type: 'ensure-defaults',
      operationId: 'p_magnitude',
      params: PARAMS,
    })
    expect(state.p_magnitude.sparsity).toBe(90)
  })

  it('reset removes an operation entirely', () => {
    const seeded: ParamsState = { p_magnitude: { sparsity: 90 } }
    const state = paramsReducer(seeded, { type: 'reset', operationId: 'p_magnitude' })
    expect(state.p_magnitude).toBeUndefined()
  })
})
