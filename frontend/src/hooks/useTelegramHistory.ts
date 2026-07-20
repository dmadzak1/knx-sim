import { useEffect, useState } from 'react'
import { fetchTelegrams } from '../api'
import type { Telegram } from '../types'

// Caps memory in a long-running browser tab, matching the backend's own
// bounded-queue philosophy (knx_sim/web/app.py's WS_QUEUE_MAXSIZE).
const MAX_TELEGRAMS = 500

/** A capped, display-oriented telegram list for the monitor table:
 * initial history via REST, then appends `lastTelegram` as new ones
 * arrive -- unless `paused`, which stops appends without affecting the
 * shared WebSocket connection (that stays live for other consumers, e.g.
 * device cards, regardless of whether the monitor view is paused). */
export function useTelegramHistory(lastTelegram: Telegram | null, paused: boolean): Telegram[] {
  const [telegrams, setTelegrams] = useState<Telegram[]>([])

  useEffect(() => {
    let cancelled = false
    fetchTelegrams()
      .then((history) => {
        if (!cancelled) setTelegrams(history)
      })
      .catch((err: unknown) => {
        console.error('Failed to load telegram history', err)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    // paused is read via closure, not listed as a dependency: React
    // re-creates this callback (closing over the latest `paused`) on
    // every render regardless, and the deps array only controls *when*
    // it's invoked. Listing `paused` here would re-run this effect (and
    // re-append the same lastTelegram) whenever pause is toggled, not
    // just when a new telegram genuinely arrives.
    if (paused || lastTelegram === null) return
    setTelegrams((prev) => {
      const next = [...prev, lastTelegram]
      return next.length > MAX_TELEGRAMS ? next.slice(next.length - MAX_TELEGRAMS) : next
    })
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- see comment above
  }, [lastTelegram])

  return telegrams
}
