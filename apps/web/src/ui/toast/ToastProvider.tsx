import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { ToastContext } from './ToastContext'
import { ToastViewport } from './Toast'
import type { ToastInput, ToastItem } from './toastTypes'

const DEFAULT_DURATION_MS = 5000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const showToast = useCallback(
    (input: ToastInput) => {
      const id = crypto.randomUUID()
      const toast: ToastItem = {
        id,
        message: input.message,
        variant: input.variant ?? 'info',
        duration: input.duration ?? DEFAULT_DURATION_MS,
      }
      setToasts((current) => [...current, toast])
      if (toast.duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismissToast(id), toast.duration),
        )
      }
      return id
    },
    [dismissToast],
  )

  const value = useMemo(
    () => ({ toasts, showToast, dismissToast }),
    [toasts, showToast, dismissToast],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismissToast} />
    </ToastContext.Provider>
  )
}
