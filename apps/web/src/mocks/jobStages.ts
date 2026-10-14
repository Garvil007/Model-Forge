import type { Operation } from '../features/catalog/generated/catalog.types'
import type { ParamValues } from '../features/catalog/types'

export interface JobStageDef {
  label: string
  /** Set only for a stage that progresses epoch by epoch rather than finishing in one step. */
  epochs?: number
}

/** TS port of `docs/ui-prototype.html`'s `stagesFor()` — same stage lists per technique, used by
 * the mock worker so `JobProgress` sees the same staged checklist the prototype simulates. */
export function stagesForOperation(operation: Operation, values: ParamValues): JobStageDef[] {
  if (operation.technique === 'convert') {
    return [
      { label: 'Loading model' },
      { label: `Converting to ${operation.label}` },
      { label: 'Checking outputs match' },
    ]
  }

  const finetune = Boolean(values.finetune)
  const tuneEpochs = Number(values.epochs) || 3
  const tune: JobStageDef[] = finetune ? [{ label: 'Fine-tuning', epochs: tuneEpochs }] : []

  switch (operation.technique) {
    case 'quantization': {
      const needsCalibration =
        ['q_int8_static', 'q_gptq', 'q_awq'].includes(operation.id) ||
        (operation.id === 'q_gguf' && Boolean(values.imatrix))
      return [
        { label: 'Loading model' },
        ...(needsCalibration ? [{ label: 'Running calibration data' }] : []),
        { label: 'Quantizing weights' },
        { label: 'Measuring accuracy' },
      ]
    }
    case 'pruning':
      return [
        { label: 'Loading model' },
        { label: 'Scoring weights' },
        { label: 'Pruning' },
        ...tune,
        { label: 'Measuring accuracy' },
      ]
    case 'distillation':
      return [
        { label: 'Loading teacher' },
        { label: 'Building student' },
        { label: 'Training student', epochs: Number(values.epochs) || 12 },
        { label: 'Measuring accuracy' },
      ]
    case 'lowrank':
      return [
        { label: 'Loading model' },
        { label: 'Decomposing layers' },
        ...tune,
        { label: 'Measuring accuracy' },
      ]
    default:
      return [
        { label: 'Loading model' },
        { label: 'Running operation' },
        { label: 'Measuring accuracy' },
      ]
  }
}

export const STAGE_DURATION_MS = 500
export const EPOCH_DURATION_MS = 60

export function stageDurationMs(stage: JobStageDef): number {
  return stage.epochs ? stage.epochs * EPOCH_DURATION_MS : STAGE_DURATION_MS
}

export function totalDurationMs(stages: JobStageDef[]): number {
  return stages.reduce((sum, stage) => sum + stageDurationMs(stage), 0)
}
