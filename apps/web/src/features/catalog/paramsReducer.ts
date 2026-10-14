import { useReducer } from 'react'
import { defaultParamValues } from './types'
import type { Param, ParamValue, ParamValues } from './types'

/** Param values for every operation touched so far, keyed by operation id — so switching
 * methods and switching back preserves what the user typed (one reducer, not per-row state). */
export type ParamsState = Record<string, ParamValues>

export type ParamsAction =
  | { type: 'ensure-defaults'; operationId: string; params: Param[] | undefined }
  | { type: 'set-value'; operationId: string; name: string; value: ParamValue }
  | { type: 'reset'; operationId: string }

export function paramsReducer(state: ParamsState, action: ParamsAction): ParamsState {
  switch (action.type) {
    case 'ensure-defaults': {
      if (state[action.operationId]) return state
      return { ...state, [action.operationId]: defaultParamValues(action.params) }
    }
    case 'set-value': {
      const current = state[action.operationId] ?? {}
      return {
        ...state,
        [action.operationId]: { ...current, [action.name]: action.value },
      }
    }
    case 'reset': {
      const rest = { ...state }
      delete rest[action.operationId]
      return rest
    }
    default:
      return state
  }
}

export function useParamsState() {
  const [state, dispatch] = useReducer(paramsReducer, {} as ParamsState)

  function valuesFor(operationId: string, params: Param[] | undefined): ParamValues {
    return state[operationId] ?? defaultParamValues(params)
  }

  function ensureDefaults(operationId: string, params: Param[] | undefined) {
    dispatch({ type: 'ensure-defaults', operationId, params })
  }

  function setValue(operationId: string, name: string, value: ParamValue) {
    dispatch({ type: 'set-value', operationId, name, value })
  }

  return { state, valuesFor, ensureDefaults, setValue, dispatch }
}
