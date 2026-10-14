import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HfImportForm } from './HfImportForm'

function renderForm(onImported = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <HfImportForm onImported={onImported} />
    </QueryClientProvider>,
  )
  return onImported
}

describe('HfImportForm', () => {
  it('shows an inline error for a malformed repo id once touched', async () => {
    renderForm()
    const input = screen.getByLabelText(/hugging face repo id/i)
    await userEvent.type(input, 'not-a-repo-id')
    await userEvent.tab()
    expect(screen.getByText(/owner\/model-name/i)).toBeInTheDocument()
  })

  it('imports a known repo and calls onImported', async () => {
    const onImported = renderForm()
    await userEvent.type(screen.getByLabelText(/hugging face repo id/i), 'microsoft/resnet-50')
    await userEvent.click(screen.getByRole('button', { name: /import from hugging face/i }))
    await vi.waitFor(() => expect(onImported).toHaveBeenCalled(), { timeout: 5000 })
    expect(onImported.mock.calls[0][0]).toMatchObject({ filename: 'resnet50.onnx' })
  })

  it('shows a gated-repo error when no token is given', async () => {
    renderForm()
    await userEvent.type(screen.getByLabelText(/hugging face repo id/i), 'meta-llama/Llama-3.2-1B')
    await userEvent.click(screen.getByRole('button', { name: /import from hugging face/i }))
    expect(await screen.findByText(/gated/i, {}, { timeout: 5000 })).toBeInTheDocument()
  })
})
