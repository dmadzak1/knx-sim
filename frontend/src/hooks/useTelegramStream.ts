import { useEffect, useRef, useState } from 'react'
import { fetchTelegrams, telegramStreamUrl } from '../api'
import type { Telegram, WsTelegramMessage } from '../types'

// Caps memory in a long-running browser tab, matching the backend's own
// bounded-queue philosophy (knx_sim/web/app.py's WS_QUEUE_MAXSIZE).
const MAX_TELEGRAMS = 500
const RECONNECT_DELAY_MS = 2000

export interface TelegramStream {
  telegrams: Telegram[]
  connected: boolean
}

/** Live telegram feed: initial history via REST, then live updates over
 * /ws, with auto-reconnect on drop. `paused` stops new telegrams from
 * being appended (the socket itself stays open) without needing to
 * reconnect when unpaused. */
export function useTelegramStream(paused: boolean): TelegramStream {
  const [telegrams, setTelegrams] = useState<Telegram[]>([])
  const [connected, setConnected] = useState(false)
  const pausedRef = useRef(paused)

  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    fetchTelegrams()
      .then((history) => {
        if (!cancelled) setTelegrams(history)
      })
      .catch((err: unknown) => {
        console.error('Failed to load telegram history', err)
      })

    function connect(): void {
      const ws = new WebSocket(telegramStreamUrl())
      socket = ws

      ws.addEventListener('open', () => setConnected(true))

      ws.addEventListener('close', () => {
        setConnected(false)
        if (!cancelled) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS)
        }
      })

      ws.addEventListener('error', () => ws.close())

      ws.addEventListener('message', (event: MessageEvent<string>) => {
        if (pausedRef.current) return
        const message = JSON.parse(event.data) as WsTelegramMessage
        if (message.type !== 'telegram') return
        setTelegrams((prev) => {
          const next = [...prev, message.data]
          return next.length > MAX_TELEGRAMS ? next.slice(next.length - MAX_TELEGRAMS) : next
        })
      })
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer !== null) clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return { telegrams, connected }
}
