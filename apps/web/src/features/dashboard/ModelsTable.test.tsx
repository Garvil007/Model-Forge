import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { ApiModel } from '../../api/types'
import { ModelsTable } from './ModelsTable'

const MODEL: ApiModel = {
  id: 'model_1',
  filename: 'resnet50.onnx',
  format: 'onnx',
  family: 'vision',
  bits: 32,
  params: 25_600_000,
  size: 102_400_000,
  inputs: null,
  metric: null,
  validationFilename: null,
  source: 'upload',
  repoId: null,
  createdAt: '2026-10-20T10:00:00.000Z',
}

function renderTable(props: Partial<React.ComponentProps<typeof ModelsTable>> = {}) {
  return render(
    <MemoryRouter>
      <ModelsTable
        models={[MODEL]}
        onCompress={vi.fn()}
        onConvert={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  )
}

describe('ModelsTable', () => {
  it('shows the empty state with an upload link when there are no models', () => {
    renderTable({ models: [] })
    expect(screen.getByText('No models yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Upload a model' })).toBeInTheDocument()
  })

  it('shows a loading skeleton while the query is pending', () => {
    renderTable({ models: [], isLoading: true })
    expect(screen.queryByText('No models yet.')).not.toBeInTheDocument()
    expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(1)
  })

  it('shows an error notice when the query fails', () => {
    renderTable({ models: [], isError: true })
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load/i)
  })

  it('lists every model with its format, size and date', () => {
    renderTable()
    expect(screen.getByText('resnet50.onnx')).toBeInTheDocument()
    expect(screen.getByText('onnx')).toBeInTheDocument()
    expect(screen.getByText('97.7 MB')).toBeInTheDocument()
  })

  it('asks for confirmation before deleting, then calls onDelete', async () => {
    const onDelete = vi.fn()
    renderTable({ onDelete })
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    const dialog = screen.getByRole('alertdialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    expect(onDelete).toHaveBeenCalledWith(MODEL)
  })

  it('calls onCompress/onConvert/onDownload for their respective buttons', async () => {
    const onCompress = vi.fn()
    const onConvert = vi.fn()
    const onDownload = vi.fn()
    renderTable({ onCompress, onConvert, onDownload })
    await userEvent.click(screen.getByRole('button', { name: 'Compress' }))
    await userEvent.click(screen.getByRole('button', { name: 'Convert' }))
    await userEvent.click(screen.getByRole('button', { name: 'Download' }))
    expect(onCompress).toHaveBeenCalledWith(MODEL)
    expect(onConvert).toHaveBeenCalledWith(MODEL)
    expect(onDownload).toHaveBeenCalledWith(MODEL)
  })
})
