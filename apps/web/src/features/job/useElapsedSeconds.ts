import { useEffect, useState } from 'react'

/** Seconds since `startedAt`, ticking every second while `running` — used by `JobProgress`'s
 * elapsed-time readout. Stops updating (freezing the final value) once `running` is false. */
export function useElapsedSeconds(startedAt: number | null, running: boolean): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!running || startedAt == null) return
    const interval = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [running, startedAt])

  if (startedAt == null) return 0
  return Math.max(0, Math.floor((now - startedAt) / 1000))
}
