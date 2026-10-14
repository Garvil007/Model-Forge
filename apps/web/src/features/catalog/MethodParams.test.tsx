import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MethodParams } from './MethodParams'
import type { ModelInfo, Param, ParamValues } from './types'

const MODEL: ModelInfo = { format: 'onnx', family: 'vision', bits: 32, params: 1e6, size: 1e6 }

describe('MethodParams', () => {
  it('renders the right primitive for every param type', () => {
    const params: Param[] = [
      {
        name: 'sel',
        label: 'Select param',
        type: 'select',
        options: [{ value: 'a', label: 'A' }],
      },
      { name: 'rng', label: 'Range param', type: 'range', min: 0, max: 100 },
      { name: 'chk', label: 'Check param', type: 'check' },
      { name: 'num', label: 'Number param', type: 'number' },
      { name: 'txt', label: 'Text param', type: 'text' },
      { name: 'fil', label: 'File param', type: 'file' },
    ]
    render(<MethodParams operation={{ params }} model={MODEL} values={{}} onChange={vi.fn()} />)
    expect(screen.getByLabelText('Select param')).toBeInTheDocument()
    expect(screen.getByLabelText('Range param')).toBeInTheDocument()
    expect(screen.getByLabelText('Check param')).toBeInTheDocument()
    expect(screen.getByLabelText('Number param')).toBeInTheDocument()
    expect(screen.getByLabelText('Text param')).toBeInTheDocument()
    expect(screen.getByLabelText('File param')).toBeInTheDocument()
  })

  it('renders nothing when there are no visible params', () => {
    const { container } = render(
      <MethodParams operation={{ params: [] }} model={MODEL} values={{}} onChange={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('marks required fields in the label', () => {
    const params: Param[] = [
      { name: 'calib', label: 'Calibration inputs', type: 'text', required: true },
    ]
    render(<MethodParams operation={{ params }} model={MODEL} values={{}} onChange={vi.fn()} />)
    expect(screen.getByLabelText('Calibration inputs (required)')).toBeInTheDocument()
  })

  it('hides a dependent field until its show-if condition is met', () => {
    const params: Param[] = [
      { name: 'imatrix', label: 'Use importance matrix', type: 'check' },
      {
        name: 'imatrix_text',
        label: 'Calibration text',
        type: 'file',
        showIf: { field: 'imatrix', equals: true },
      },
    ]
    const { rerender } = render(
      <MethodParams
        operation={{ params }}
        model={MODEL}
        values={{ imatrix: false }}
        onChange={vi.fn()}
      />,
    )
    expect(screen.queryByLabelText('Calibration text')).not.toBeInTheDocument()

    rerender(
      <MethodParams
        operation={{ params }}
        model={MODEL}
        values={{ imatrix: true }}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByLabelText('Calibration text')).toBeInTheDocument()
  })

  it('applies defaults by rendering the default value', () => {
    const params: Param[] = [
      {
        name: 'qtype',
        label: 'Quant type',
        type: 'select',
        default: 'b',
        options: [
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ],
      },
    ]
    const values: ParamValues = { qtype: 'b' }
    render(<MethodParams operation={{ params }} model={MODEL} values={values} onChange={vi.fn()} />)
    expect(screen.getByLabelText('Quant type')).toHaveValue('b')
  })

  it('falls back to the param default when no value has been seeded yet', () => {
    const params: Param[] = [
      {
        name: 'samples',
        label: 'Samples to use',
        type: 'range',
        min: 50,
        max: 1000,
        step: 50,
        default: 300,
      },
    ]
    render(<MethodParams operation={{ params }} model={MODEL} values={{}} onChange={vi.fn()} />)
    expect(screen.getByLabelText('Samples to use')).toHaveValue('300')
  })

  it('reports the new value through onChange when the user edits a field', async () => {
    const onChange = vi.fn()
    const params: Param[] = [{ name: 'name', label: 'Name param', type: 'text' }]
    render(<MethodParams operation={{ params }} model={MODEL} values={{}} onChange={onChange} />)
    await userEvent.type(screen.getByLabelText('Name param'), 'x')
    expect(onChange).toHaveBeenCalledWith('name', 'x')
  })
})
