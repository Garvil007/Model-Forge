import type { Param, ParamValues } from './types'

/** Evaluate one param's show-if rule against the operation's current values — port of the
 * prototype's `p.show(values(op))` closures, made declarative. */
export function isParamShown(param: Param, values: ParamValues, modelFormat: string): boolean {
  if (param.onlyFor && param.onlyFor.length > 0 && !param.onlyFor.includes(modelFormat)) {
    return false
  }
  if (!param.showIf) return true
  return values[param.showIf.field] === param.showIf.equals
}

export function visibleParams(
  params: Param[] | undefined,
  values: ParamValues,
  modelFormat: string,
): Param[] {
  return (params ?? []).filter((param) => isParamShown(param, values, modelFormat))
}

/** Labels of required, currently-visible params with no value yet — port of the prototype's
 * `missingRequired()`. */
export function missingRequiredLabels(
  params: Param[] | undefined,
  values: ParamValues,
  modelFormat: string,
): string[] {
  return visibleParams(params, values, modelFormat)
    .filter((param) => param.required && !values[param.name])
    .map((param) => param.label)
}
