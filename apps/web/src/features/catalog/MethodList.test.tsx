import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MethodList } from './MethodList'
import type { ModelInfo, Operation } from './types'

const AVAILABLE: Operation = {
  id: 'available_op',
  technique: 'quantization',
  label: 'Available op',
  description: 'Works on this model.',
  accuracy: 'lossless',
  typicalImpact: 'no change',
  timeEstimate: 'seconds',
  sourceFormats: ['onnx'],
  workerImage: 'cpu-base',
  queue: 'cpu',
}

const UNAVAILABLE: Operation = {
  ...AVAILABLE,
  id: 'unavailable_op',
  label: 'Unavailable op',
  sourceFormats: ['torch'],
}

const MODEL: ModelInfo = { format: 'onnx', family: 'vision', bits: 32, params: 1e6, size: 1e6 }

describe('MethodList', () => {
  it('shows an empty message with no model', () => {
    render(
      <MethodList operations={[AVAILABLE]} model={null} selectedId={null} onSelect={vi.fn()} />,
    )
    expect(screen.getByText(/Upload a model/)).toBeInTheDocument()
  })

  it('sorts available operations above unavailable ones regardless of input order', () => {
    render(
      <MethodList
        operations={[UNAVAILABLE, AVAILABLE]}
        model={MODEL}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    )
    const names = screen.getAllByRole('radio').map((el) => el.id)
    expect(names).toEqual(['op-available_op', 'op-unavailable_op'])
  })

  it('shows the disabled reason instead of metadata for unavailable methods', () => {
    render(
      <MethodList operations={[UNAVAILABLE]} model={MODEL} selectedId={null} onSelect={vi.fn()} />,
    )
    expect(screen.getByText(/Not available for ONNX/)).toBeInTheDocument()
    expect(screen.queryByText(/Typical impact/)).not.toBeInTheDocument()
  })

  it('shows typical-impact/takes metadata for available methods', () => {
    render(
      <MethodList operations={[AVAILABLE]} model={MODEL} selectedId={null} onSelect={vi.fn()} />,
    )
    expect(screen.getByText(/Typical impact:/)).toBeInTheDocument()
    expect(screen.getByText(/Takes:/)).toBeInTheDocument()
  })

  it('cannot select a disabled method', () => {
    render(
      <MethodList operations={[UNAVAILABLE]} model={MODEL} selectedId={null} onSelect={vi.fn()} />,
    )
    expect(screen.getByRole('radio')).toBeDisabled()
  })

  it('renders renderSelected only inside the selected row', () => {
    render(
      <MethodList
        operations={[AVAILABLE]}
        model={MODEL}
        selectedId="available_op"
        onSelect={vi.fn()}
        renderSelected={(op) => <div data-testid="details">{op.id} details</div>}
      />,
    )
    expect(screen.getByTestId('details')).toHaveTextContent('available_op details')
  })

  it('selects an available method by clicking its label', async () => {
    const onSelect = vi.fn()
    render(
      <MethodList operations={[AVAILABLE]} model={MODEL} selectedId={null} onSelect={onSelect} />,
    )
    await userEvent.click(screen.getByText('Available op'))
    expect(onSelect).toHaveBeenCalledWith('available_op')
  })
})
