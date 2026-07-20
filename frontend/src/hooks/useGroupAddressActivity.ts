import { useEffect, useRef, useState } from 'react'
import type { Telegram } from '../types'

export interface GroupAddressActivity {
  groupAddress: string
  lastValue: unknown
  lastSeen: number
  count: number
  ratePerMinute: number
}

const RATE_WINDOW_MS = 60_000
const MAX_TIMESTAMPS_PER_GA = 100

/** Per-GA "last value + rate" aggregate (F-WEB-3), built incrementally off
 * the live telegram stream -- cheap regardless of how long the dashboard
 * has been open, unlike re-deriving from a growing telegram history on
 * every render. Rate is messages-per-minute within a rolling 60s window. */
export function useGroupAddressActivity(lastTelegram: Telegram | null): GroupAddressActivity[] {
  const timestampsByGa = useRef(new Map<string, number[]>())
  const [activityByGa, setActivityByGa] = useState(new Map<string, GroupAddressActivity>())

  useEffect(() => {
    if (lastTelegram === null || lastTelegram.service === 'read') return
    const { destination, value, timestamp } = lastTelegram
    const nowMs = timestamp * 1000
    const cutoff = nowMs - RATE_WINDOW_MS

    const timestamps = timestampsByGa.current.get(destination) ?? []
    timestamps.push(nowMs)
    const recent = timestamps.filter((t) => t >= cutoff).slice(-MAX_TIMESTAMPS_PER_GA)
    timestampsByGa.current.set(destination, recent)

    setActivityByGa((prev) => {
      const next = new Map(prev)
      const previousCount = next.get(destination)?.count ?? 0
      next.set(destination, {
        groupAddress: destination,
        lastValue: value,
        lastSeen: timestamp,
        count: previousCount + 1,
        ratePerMinute: recent.length,
      })
      return next
    })
  }, [lastTelegram])

  return Array.from(activityByGa.values()).sort((a, b) => b.lastSeen - a.lastSeen)
}
