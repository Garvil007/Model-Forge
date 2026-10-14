import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { MethodParams } from './MethodParams'
import { getOperationById } from './types'
import type { ModelInfo, ParamValues } from './types'

const meta: Meta<typeof MethodParams> = {
  title: 'Catalog/MethodParams',
  component: MethodParams,
}

export default meta
type Story = StoryObj<typeof MethodParams>

const VISION_MODEL: ModelInfo = {
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25.6e6,
  size: 102_442_450,
}
const LLM_MODEL: ModelInfo = {
  format: 'safetensors',
  family: 'llm',
  bits: 16,
  params: 1.236e9,
  size: 2_471_645_608,
}

function Demo({ operationId, model }: { operationId: string; model: ModelInfo }) {
  const operation = getOperationById(operationId)!
  const [values, setValues] = useState<ParamValues>({})
  return (
    <MethodParams
      operation={operation}
      model={model}
      values={values}
      onChange={(name, value) => setValues((v) => ({ ...v, [name]: value }))}
    />
  )
}

export const INT8Static: Story = {
  render: () => <Demo operationId="q_int8_static" model={VISION_MODEL} />,
}

export const GGUFWithShowIf: Story = {
  name: 'GGUF (toggle a show-if field)',
  render: () => <Demo operationId="q_gguf" model={LLM_MODEL} />,
}

export const StructuredPruningWithFinetune: Story = {
  render: () => <Demo operationId="p_structured" model={VISION_MODEL} />,
}

export const Empty: Story = {
  name: 'Empty (no params)',
  render: () => <Demo operationId="c_onnx" model={VISION_MODEL} />,
}
