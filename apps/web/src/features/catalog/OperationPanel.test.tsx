import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { ApiModel } from '../../api/types'
import { OperationPanel } from './OperationPanel'

const MODEL: ApiModel = {
  id: 'model-1',
  filename: 'resnet50.onnx',
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25.6e6,
  size: 102_442_450,
  inputs: 'input [batch, 3, 224, 224]',
  metric: ['Top-1 accuracy (ImageNet val)', 76.1, '%'],
  validationFilename: null,
  source: 'upload',
  repoId: null,
  createdAt: new Date().toISOString(),
}

function renderPanel() {
  const queryClient = new QueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OperationPanel model={MODEL} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('OperationPanel', () => {
  it('shows the technique table and methods on the Compress tab by default', () => {
    renderPanel()
    expect(screen.getByRole('tab', { name: 'Compress' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('radiogroup', { name: 'Compression technique' })).toBeInTheDocument()
    expect(screen.getByText('Method')).toBeInTheDocument()
  })

  it('switches to convert targets on the Convert tab', async () => {
    renderPanel()
    const user = userEvent.setup()
    await user.click(screen.getByRole('tab', { name: 'Convert' }))
    expect(screen.queryByRole('radiogroup', { name: 'Compression technique' })).not.toBeInTheDocument()
    expect(screen.getByText('Convert to')).toBeInTheDocument()
  })

  it('shows method params and a run button once a method is selected', async () => {
    renderPanel()
    const user = userEvent.setup()
    const availableMethod = screen.getByRole('radio', { name: 'INT8 dynamic' })
    await user.click(availableMethod)
    expect(screen.getByText(/Estimated output:/)).toBeInTheDocument()
  })
})
