import catalogJson from './generated/catalog.json'
import type { Catalog, Operation, Param, Technique } from './generated/catalog.types'

export type {
  Catalog,
  Operation,
  Param,
  ParamOption,
  ShowIf,
  Technique,
} from './generated/catalog.types'

/** A model's known properties, as detected from its file or sample metadata — mirrors the
 * catalog package's ModelInfo (packages/catalog/src/modelforge_catalog/models.py). */
export interface ModelInfo {
  format: string
  family: string
  bits: number
  params: number
  size: number
}

export type ParamValue = string | number | boolean | null | undefined

/** Current param values for one operation, keyed by param name. */
export type ParamValues = Record<string, ParamValue>

export const CATALOG = catalogJson as Catalog

export function getTechniques(): Technique[] {
  return CATALOG.techniques
}

export function getMethods(): Operation[] {
  return CATALOG.operations.filter((op) => op.technique !== 'convert')
}

export function getConverts(): Operation[] {
  return CATALOG.operations.filter((op) => op.technique === 'convert')
}

export function getMethodsForTechnique(techniqueId: string): Operation[] {
  return getMethods().filter((op) => op.technique === techniqueId)
}

export function getOperationById(id: string): Operation | undefined {
  return CATALOG.operations.find((op) => op.id === id)
}

export function defaultParamValues(params: Param[] | undefined): ParamValues {
  const values: ParamValues = {}
  for (const param of params ?? []) {
    if (param.default !== undefined) {
      values[param.name] = param.default as ParamValue
    }
  }
  return values
}
