import type { Telegram } from './types'

export async function fetchTelegrams(limit = 200): Promise<Telegram[]> {
  const response = await fetch(`/api/telegrams?limit=${limit}`)
  if (!response.ok) {
    throw new Error(`GET /api/telegrams failed: ${response.status}`)
  }
  return (await response.json()) as Telegram[]
}

export function telegramStreamUrl(): string {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${location.host}/ws`
}
