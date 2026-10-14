import type { Meta, StoryObj } from '@storybook/react-vite'
import { ResultPanel } from './ResultPanel'

const meta: Meta<typeof ResultPanel> = {
  title: 'Job/ResultPanel',
  component: ResultPanel,
  args: {
    operationLabel: 'FP16 weights',
    beforeBytes: 102_442_450,
    afterBytes: 51_221_225,
    beforeWidthPercent: 100,
    afterWidthPercent: 50,
    downloadName: 'resnet50_fp16.onnx',
    onDownload: () => {},
    onTryOtherSettings: () => {},
  },
}

export default meta
type Story = StoryObj<typeof ResultPanel>

export const SimilarityOnly: Story = {
  args: {
    headline: '50% smaller',
    speedNote: 'about 2 to 3 times faster on CPU',
    metrics: [{ label: 'Output similarity', value: '0.99812' }],
    measuredOnValidation: false,
  },
}

export const RealValidationAccuracy: Story = {
  args: {
    headline: '50% smaller',
    speedNote: null,
    metrics: [{ label: 'Top-1 accuracy (ImageNet val)', value: '75.8% (was 76.1%)' }],
    measuredOnValidation: true,
  },
}

export const PerplexityForLlm: Story = {
  args: {
    headline: '75% smaller',
    speedNote: 'runs on CPU with llama.cpp',
    metrics: [
      { label: 'Perplexity (WikiText-2)', value: '9.75 before, 9.91 after (lower is better)' },
    ],
    measuredOnValidation: true,
    downloadName: 'llama-3.2-1b_q4-k-m.gguf',
  },
}
