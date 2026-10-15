import { useCallback, useRef, useState } from 'react'
import { apiClient } from '../../api/client'
import type { ApiModel, CreateUploadResponse } from '../../api/types'
import type { DetectedModel, UploadProgressState } from './types'

const MAX_PART_ATTEMPTS = 4
const RETRY_BASE_DELAY_MS = 400
const PAUSE_POLL_MS = 150

const IDLE_STATE: UploadProgressState = {
  status: 'idle',
  bytesUploaded: 0,
  totalBytes: 0,
  bytesPerSecond: 0,
  secondsRemaining: null,
  error: null,
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export class UploadCanceledError extends Error {}

export interface UseFileUploadResult {
  state: UploadProgressState
  /** Runs the full S3-style multipart flow (create upload, PUT every part with per-part retry,
   * complete) and resolves with the registered model. */
  start: (file: File, detected: DetectedModel) => Promise<ApiModel>
  pause: () => void
  resume: () => void
  cancel: () => void
  reset: () => void
}

/** Drives a browser-side multipart upload against the mock (or, later, real) `/uploads`
 * endpoints — chunks the file into `partSize`-sized pieces per `POST /api/uploads`'s response,
 * uploads them in order with retry-with-backoff per part, and reports speed/ETA/pause state the
 * UI can render as a progress bar. */
export function useFileUpload(): UseFileUploadResult {
  const [state, setState] = useState<UploadProgressState>(IDLE_STATE)
  const pausedRef = useRef(false)
  const canceledRef = useRef(false)

  const pause = useCallback(() => {
    pausedRef.current = true
    setState((s) => (s.status === 'uploading' ? { ...s, status: 'paused' } : s))
  }, [])

  const resume = useCallback(() => {
    pausedRef.current = false
    setState((s) => (s.status === 'paused' ? { ...s, status: 'uploading' } : s))
  }, [])

  const cancel = useCallback(() => {
    canceledRef.current = true
  }, [])

  const reset = useCallback(() => {
    pausedRef.current = false
    canceledRef.current = false
    setState(IDLE_STATE)
  }, [])

  const start = useCallback(async (file: File, detected: DetectedModel): Promise<ApiModel> => {
    canceledRef.current = false
    pausedRef.current = false
    const startedAt = Date.now()
    let bytesUploaded = 0

    setState({ ...IDLE_STATE, status: 'uploading', totalBytes: file.size })

    let upload: CreateUploadResponse
    try {
      upload = await apiClient.post<CreateUploadResponse>('/uploads', {
        filename: file.name,
        size: file.size,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not start the upload.'
      setState((s) => ({ ...s, status: 'error', error: message }))
      throw error
    }

    for (let partNumber = 1; partNumber <= upload.totalParts; partNumber++) {
      while (pausedRef.current) {
        if (canceledRef.current) throw new UploadCanceledError('Upload canceled.')
        await sleep(PAUSE_POLL_MS)
      }
      if (canceledRef.current) throw new UploadCanceledError('Upload canceled.')

      const rangeStart = (partNumber - 1) * upload.partSize
      const rangeEnd = Math.min(file.size, rangeStart + upload.partSize)
      const chunk = file.slice(rangeStart, rangeEnd)

      for (let attempt = 1; ; attempt++) {
        try {
          await apiClient.putPresigned(upload.partUrls[partNumber - 1], chunk)
          break
        } catch (error) {
          if (attempt >= MAX_PART_ATTEMPTS) {
            const message = `Part ${partNumber} failed to upload after ${attempt} attempts.`
            setState((s) => ({ ...s, status: 'error', error: message }))
            throw error
          }
          await sleep(RETRY_BASE_DELAY_MS * 2 ** (attempt - 1))
        }
      }

      bytesUploaded += chunk.size
      const elapsedSeconds = Math.max(0.001, (Date.now() - startedAt) / 1000)
      const bytesPerSecond = bytesUploaded / elapsedSeconds
      const remainingBytes = file.size - bytesUploaded
      setState({
        status: 'uploading',
        bytesUploaded,
        totalBytes: file.size,
        bytesPerSecond,
        secondsRemaining: bytesPerSecond > 0 ? remainingBytes / bytesPerSecond : null,
        error: null,
      })
    }

    setState((s) => ({ ...s, status: 'completing' }))
    const model = await apiClient.post<ApiModel>(`/uploads/${upload.uploadId}/complete`, {
      uploadId: upload.uploadId,
      model: detected,
    })
    setState((s) => ({ ...s, status: 'done' }))
    return model
  }, [])

  return { state, start, pause, resume, cancel, reset }
}
