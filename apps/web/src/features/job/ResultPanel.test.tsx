import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ResultPanel } from './ResultPanel'

function renderPanel(overrides: Partial<Parameters<typeof ResultPanel>[0]> = {}) {
  return render(
    <ResultPanel
      headline="60% smaller"
      operationLabel="FP16 weights"
      speedNote={null}
      beforeBytes={100_000_000}
      afterBytes={40_000_000}
      beforeWidthPercent={100}
      afterWidthPercent={40}
      metrics={[{ label: 'Output similarity', value: '0.99812' }]}
      measuredOnValidation={false}
      downloadName="resnet50_fp16.onnx"
      onDownload={vi.fn()}
      onTryOtherSettings={vi.fn()}
      {...overrides}
    />,
  )
}

describe('ResultPanel', () => {
  it('shows the headline, metrics table and the similarity disclaimer', () => {
    renderPanel()
    expect(screen.getByText('60% smaller')).toBeInTheDocument()
    expect(screen.getByText('0.99812')).toBeInTheDocument()
    expect(screen.getByText(/add validation data to see real accuracy/i)).toBeInTheDocument()
  })

  it('shows the validation-measured note instead when measuredOnValidation is true', () => {
    renderPanel({ measuredOnValidation: true })
    expect(screen.getByText(/measured on the validation set/i)).toBeInTheDocument()
  })

  it('fires download and try-other-settings callbacks', async () => {
    const onDownload = vi.fn()
    const onTryOtherSettings = vi.fn()
    renderPanel({ onDownload, onTryOtherSettings })
    await userEvent.click(screen.getByRole('button', { name: /download resnet50_fp16.onnx/i }))
    await userEvent.click(screen.getByRole('button', { name: /try other settings/i }))
    expect(onDownload).toHaveBeenCalledOnce()
    expect(onTryOtherSettings).toHaveBeenCalledOnce()
  })
})
