export type ToastVariant = 'info' | 'success' | 'warning' | 'error'

export interface ToastInput {
  message: string
  variant?: ToastVariant
  duration?: number
}

export interface ToastItem extends ToastInput {
  id: string
  variant: ToastVariant
  duration: number
}

export interface ToastContextValue {
  toasts: ToastItem[]
  showToast: (toast: ToastInput) => string
  dismissToast: (id: string) => void
}
