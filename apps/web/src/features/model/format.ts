import { formatBytes } from '../catalog/sizeEstimateFormulas'

export { formatBytes }

/** Port of `docs/ui-prototype.html`'s `fmtParams` (line 508). */
export function formatParams(n: number): string {
  return n >= 1e9 ? `${(n / 1e9).toFixed(2)} billion` : `${(n / 1e6).toFixed(1)} million`
}

/** `bytesPerSecond` formatted for the upload progress row, e.g. "4.2 MB/s". */
export function formatSpeed(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`
}

/** Seconds formatted as "Xm Ys" or "Ys", for upload time-remaining. */
export function formatDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(rounded / 60)
  const secs = rounded % 60
  return minutes > 0 ? `${minutes}m ${secs}s` : `${secs}s`
}
