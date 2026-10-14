import { FileInput } from '../../ui/FileInput/FileInput'
import { NumberInput } from '../../ui/NumberInput/NumberInput'
import { Range } from '../../ui/Range/Range'
import { Select } from '../../ui/Select/Select'
import { TextInput } from '../../ui/TextInput/TextInput'
import { Toggle } from '../../ui/Toggle/Toggle'
import styles from './MethodParams.module.css'
import { visibleParams } from './paramVisibility'
import type { ModelInfo, Param, ParamValue, ParamValues } from './types'

function withRequiredMark(label: string, required: boolean | undefined): string {
  return required ? `${label} (required)` : label
}

export interface ParamFieldProps {
  param: Param
  value: ParamValue
  onChange: (value: ParamValue) => void
}

/** Renders the one primitive that matches `param.type` — the single place that knows how a
 * catalog param type maps to a UI control. Adding a new param to the catalog reuses one of the
 * existing types and needs no change here; adding a wholly new param *type* is the only case
 * that would. */
export function ParamField({ param, value, onChange }: ParamFieldProps) {
  const label = withRequiredMark(param.label, param.required)

  const effective = value ?? param.default

  switch (param.type) {
    case 'select':
      return (
        <Select
          label={label}
          help={param.help}
          options={param.options ?? []}
          value={effective == null ? '' : String(effective)}
          onChange={(event) => onChange(event.target.value)}
        />
      )
    case 'range':
      return (
        <Range
          label={label}
          help={param.help}
          unit={param.unit}
          min={param.min}
          max={param.max}
          step={param.step}
          value={effective == null ? (param.min ?? 0) : Number(effective)}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      )
    case 'check':
      return (
        <div className={styles.checkField}>
          <Toggle
            label={label}
            checked={Boolean(effective)}
            onChange={(event) => onChange(event.target.checked)}
          />
          {param.help && <small className={styles.checkHelp}>{param.help}</small>}
        </div>
      )
    case 'number':
      return (
        <NumberInput
          label={label}
          help={param.help}
          min={param.min}
          max={param.max}
          value={effective == null ? '' : Number(effective)}
          onChange={(event) =>
            onChange(event.target.value === '' ? null : Number(event.target.value))
          }
        />
      )
    case 'text':
      return (
        <TextInput
          label={label}
          help={param.help}
          value={effective == null ? '' : String(effective)}
          onChange={(event) => onChange(event.target.value)}
        />
      )
    case 'file':
      return (
        <FileInput
          label={param.label}
          help={value ? `Selected: ${value}` : param.help}
          required={param.required}
          accept={param.accept}
          onChange={(event) => onChange(event.target.files?.[0]?.name ?? null)}
        />
      )
    default:
      return null
  }
}

export interface MethodParamsProps {
  operation: { params?: Param[] }
  model: ModelInfo
  values: ParamValues
  onChange: (name: string, value: ParamValue) => void
}

/** Schema-driven params panel for one operation — filters to currently-visible params (show-if
 * + onlyFor) and renders each with `ParamField`. Renders nothing when there's nothing to show. */
export function MethodParams({ operation, model, values, onChange }: MethodParamsProps) {
  const params = visibleParams(operation.params, values, model.format)
  if (params.length === 0) return null

  return (
    <div className={styles.params}>
      {params.map((param) => (
        <ParamField
          key={param.name}
          param={param}
          value={values[param.name]}
          onChange={(value) => onChange(param.name, value)}
        />
      ))}
    </div>
  )
}
