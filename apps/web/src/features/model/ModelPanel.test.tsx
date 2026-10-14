import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { resetScenarios, setScenarios } from '../../mocks/scenarios'
import { MAX_FILE_BYTES } from './detectFormat'
import { ModelPanel } from './ModelPanel'

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ModelPanel />
    </QueryClientProvider>,
  )
}

function uploadInput() {
  return screen.getByLabelText(/drop a model file here/i)
}

beforeEach(() => {
  resetScenarios()
})

describe('ModelPanel', () => {
  it('uploads a file end to end and shows the detected details', async () => {
    renderPanel()
    const file = new File(['weights'], 'resnet50.onnx', { type: 'application/octet-stream' })
    await userEvent.upload(uploadInput(), file)

    expect(await screen.findByText(/checking your model/i)).toBeInTheDocument()
    expect(await screen.findByText('resnet50.onnx')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/checking your model/i)).not.toBeInTheDocument())
    await waitFor(
      () =>
        expect(screen.queryByRole('group', { name: /upload progress/i })).not.toBeInTheDocument(),
      {
        timeout: 8000,
      },
    )
    expect(screen.queryByText(/failed to upload/i)).not.toBeInTheDocument()
  })

  it('retries a part that fails twice and then succeeds', async () => {
    setScenarios({ uploadFailPart: 1 })
    renderPanel()
    const file = new File(['weights'], 'mobilenet.onnx', { type: 'application/octet-stream' })
    await userEvent.upload(uploadInput(), file)

    expect(await screen.findByText('mobilenet.onnx')).toBeInTheDocument()
    await waitFor(
      () =>
        expect(screen.queryByRole('group', { name: /upload progress/i })).not.toBeInTheDocument(),
      { timeout: 10000 },
    )
    expect(screen.queryByText(/failed to upload/i)).not.toBeInTheDocument()
  })

  it('rejects an unsupported file type before any request goes out', async () => {
    renderPanel()
    const file = new File(['data'], 'weights.xyz', { type: 'application/octet-stream' })
    await userEvent.upload(uploadInput(), file, { applyAccept: false })

    expect(await screen.findByText(/aren't supported/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('shows a detection failure for an oversized file', async () => {
    renderPanel()
    const file = new File(['data'], 'huge.onnx', { type: 'application/octet-stream' })
    Object.defineProperty(file, 'size', { value: MAX_FILE_BYTES + 1 })
    await userEvent.upload(uploadInput(), file)

    expect(await screen.findByText(/too large/i)).toBeInTheDocument()
  })

  it('loads a sample model immediately with no upload', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /resnet-50/i }))

    expect(await screen.findByText('resnet50.onnx')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: /upload progress/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/checking your model/i)).not.toBeInTheDocument()
  })
})
