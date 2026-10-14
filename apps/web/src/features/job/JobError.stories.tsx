import type { Meta, StoryObj } from '@storybook/react-vite'
import { JobError } from './JobError'

const meta: Meta<typeof JobError> = {
  title: 'Job/JobError',
  component: JobError,
  args: { onRetry: () => {}, onAdjustSettings: () => {} },
}

export default meta
type Story = StoryObj<typeof JobError>

export const OutOfMemory: Story = {
  args: {
    error: {
      code: 'out_of_memory',
      message:
        'The worker ran out of memory while processing this model. Try a smaller batch size, a lighter method, or a larger instance.',
    },
  },
}

export const UnsupportedOperator: Story = {
  args: {
    error: {
      code: 'unsupported_operator',
      operator: 'aten::_scaled_dot_product_flash_attention',
      message:
        "This model uses the operator aten::_scaled_dot_product_flash_attention, which this conversion target doesn't support yet.",
    },
  },
}

export const BadCalibrationData: Story = {
  args: {
    error: {
      code: 'bad_calibration_data',
      message:
        "Your calibration data couldn't be used — check that it's unlabeled example inputs in the format this operation expects, then try again.",
    },
  },
}

export const GatedModel: Story = {
  args: {
    error: {
      code: 'gated_model',
      message:
        "This model's weights are gated and the access token on file doesn't have permission to run this operation.",
    },
  },
}

export const QuotaExceeded: Story = {
  args: {
    error: {
      code: 'quota_exceeded',
      message: "You've used all of your plan's compute quota for this period.",
    },
  },
}

export const SpotInterrupted: Story = {
  args: {
    error: {
      code: 'spot_interrupted',
      message:
        'The spot instance running this job was reclaimed partway through. No progress is lost — retry to pick up a new instance.',
    },
  },
}
