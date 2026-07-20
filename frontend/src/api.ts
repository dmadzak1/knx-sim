import type { DeviceState, InjectRequest, Telegram } from './types'

export async function fetchTelegrams(limit = 200): Promise<Telegram[]> {
  const response = await fetch(`/api/telegrams?limit=${limit}`)
  if (!response.ok) {
    throw new Error(`GET /api/telegrams failed: ${response.status}`)
  }
  return (await response.json()) as Telegram[]
}

export async function fetchDevices(): Promise<DeviceState[]> {
  const response = await fetch('/api/devices')
  if (!response.ok) {
    throw new Error(`GET /api/devices failed: ${response.status}`)
  }
  return (await response.json()) as DeviceState[]
}

export async function injectTelegram(request: InjectRequest): Promise<void> {
  const response = await fetch('/api/inject', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`POST /api/inject failed (${response.status}): ${detail}`)
  }
}

export function telegramStreamUrl(): string {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${location.host}/ws`
}
