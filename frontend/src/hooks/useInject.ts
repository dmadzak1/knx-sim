import { useCallback, useState } from 'react'
import { injectTelegram } from '../api'
import type { InjectRequest } from '../types'

export interface UseInject {
  inject: (request: InjectRequest) => Promise<void>
  pending: boolean
  error: string | null
}

/** Wraps POST /api/inject with pending/error state, shared by every
 * device-card control and the manual injector form so failures (e.g. a
 * malformed value) surface in the UI instead of failing silently. */
export function useInject(): UseInject {
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const inject = useCallback(async (request: InjectRequest) => {
    setPending(true)
    setError(null)
    try {
      await injectTelegram(request)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }, [])

  return { inject, pending, error }
}
