import { useEffect, useState } from 'react'

/** Delays reflecting `value` until it's stopped changing for `delayMs` — used so dragging a
 * range slider doesn't recompute the size estimate on every intermediate position. */
export function useDebouncedValue<T>(value: T, delayMs = 150): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
