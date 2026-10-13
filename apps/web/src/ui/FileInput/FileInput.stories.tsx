import type { Meta, StoryObj } from '@storybook/react-vite'
import { DropZone, FileInput } from './FileInput'

const meta: Meta = {
  title: 'UI/FileInput',
}

export default meta

export const DropZoneDefault: StoryObj<typeof DropZone> = {
  render: () => (
    <DropZone
      title="Drop a model file here"
      hint="or click to choose one"
      accept=".onnx,.tflite,.pt"
    />
  ),
}

export const PlainField: StoryObj<typeof FileInput> = {
  render: () => (
    <FileInput
      label="Calibration inputs"
      accept=".zip,.npz,.npy"
      required
      help="100 to 1,000 real inputs. No labels needed."
    />
  ),
}
