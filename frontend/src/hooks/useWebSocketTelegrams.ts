import { useEffect, useState } from 'react'
import { telegramStreamUrl } from '../api'
import type { Telegram, WsTelegramMessage } from '../types'

const RECONNECT_DELAY_MS = 2000

export interface WebSocketTelegrams {
  lastTelegram: Telegram | null
  connected: boolean
}

/** Owns the single shared WebSocket connection to /ws, auto-reconnecting
 * on drop. Exposes only the most recently received telegram, not a
 * growing list -- consumers that need a history (the monitor table) or
 * derived aggregates (device state, GA activity) build their own bounded
 * state incrementally off `lastTelegram` rather than everyone re-scanning
 * a shared array on every message. Call this once (in App) and pass
 * `lastTelegram`/`connected` down, rather than calling it from multiple
 * components -- each call opens its own socket and its own
 * bus.subscribe() on the backend. */
export function useWebSocketTelegrams(): WebSocketTelegrams {
  const [lastTelegram, setLastTelegram] = useState<Telegram | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

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
        const message = JSON.parse(event.data) as WsTelegramMessage
        if (message.type === 'telegram') setLastTelegram(message.data)
      })
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer !== null) clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return { lastTelegram, connected }
}
