import type { Meta, StoryObj } from '@storybook/react-vite'
import { DetectedDetails } from './DetectedDetails'
import { SAMPLE_MODELS } from './sampleModels'

const meta: Meta<typeof DetectedDetails> = {
  title: 'Model/DetectedDetails',
  component: DetectedDetails,
}
export default meta
type Story = StoryObj<typeof DetectedDetails>

const noop = () => {}

export const Vision: Story = {
  args: { model: SAMPLE_MODELS.resnet, onFamilyChange: noop, onValidationFile: noop },
}

export const Llm: Story = {
  args: { model: SAMPLE_MODELS.llama, onFamilyChange: noop, onValidationFile: noop },
}

export const Gguf: Story = {
  args: {
    model: { ...SAMPLE_MODELS.llama, filename: 'llama.gguf', format: 'gguf', bits: 4.8 },
    onFamilyChange: noop,
    onValidationFile: noop,
  },
}
