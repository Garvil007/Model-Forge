import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { MethodList } from './MethodList'
import { MethodParams } from './MethodParams'
import { SizeEstimate } from './SizeEstimate'
import { getMethodsForTechnique, getOperationById } from './types'
import type { ModelInfo, ParamValues } from './types'

const meta: Meta<typeof MethodList> = {
  title: 'Catalog/MethodList',
  component: MethodList,
}

export default meta
type Story = StoryObj<typeof MethodList>

const VISION_MODEL: ModelInfo = {
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25.6e6,
  size: 102_442_450,
}

const QUANTIZATION_METHODS = getMethodsForTechnique('quantization')

export const Default: Story = {
  name: 'Default (with params + size estimate)',
  render: () => {
    function Demo() {
      const [selectedId, setSelectedId] = useState<string | null>(null)
      const [allValues, setAllValues] = useState<Record<string, ParamValues>>({})
      return (
        <MethodList
          operations={QUANTIZATION_METHODS}
          model={VISION_MODEL}
          selectedId={selectedId}
          onSelect={setSelectedId}
          renderSelected={(operation) => {
            const values = allValues[operation.id] ?? {}
            return (
              <>
                <MethodParams
                  operation={operation}
                  model={VISION_MODEL}
                  values={values}
                  onChange={(name, value) =>
                    setAllValues((prev) => ({
                      ...prev,
                      [operation.id]: { ...prev[operation.id], [name]: value },
                    }))
                  }
                />
                <SizeEstimate operationId={operation.id} model={VISION_MODEL} values={values} />
              </>
            )
          }}
        />
      )
    }
    return <Demo />
  },
}

export const Empty: Story = {
  name: 'Empty (no model)',
  render: () => (
    <MethodList
      operations={QUANTIZATION_METHODS}
      model={null}
      selectedId={null}
      onSelect={() => {}}
    />
  ),
}

export const AllDisabled: Story = {
  name: 'All disabled (GGUF file, already quantized)',
  render: () => {
    const ggufModel: ModelInfo = {
      format: 'gguf',
      family: 'llm',
      bits: 4.8,
      params: 1e9,
      size: 5e8,
    }
    return (
      <MethodList
        operations={QUANTIZATION_METHODS}
        model={ggufModel}
        selectedId={null}
        onSelect={() => {}}
      />
    )
  },
}

export const ConvertTargets: Story = {
  render: () => {
    const operations = [
      getOperationById('c_onnx')!,
      getOperationById('c_tflite')!,
      getOperationById('c_coreml')!,
    ]
    return (
      <MethodList
        operations={operations}
        model={VISION_MODEL}
        selectedId={null}
        onSelect={() => {}}
      />
    )
  },
}
