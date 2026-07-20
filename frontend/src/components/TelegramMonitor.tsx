import { useEffect, useMemo, useRef, useState } from 'react'
import { useTelegramHistory } from '../hooks/useTelegramHistory'
import type { Telegram } from '../types'

type ServiceFilter = 'all' | Telegram['service']

function formatTime(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return date.toLocaleTimeString(undefined, { hour12: false }) + `.${String(date.getMilliseconds()).padStart(3, '0')}`
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') {
    const control = value as { direction?: unknown; step_code?: unknown }
    if ('direction' in control && 'step_code' in control) {
      return `${control.direction ? 'up' : 'down'}, step ${String(control.step_code)}`
    }
    return JSON.stringify(value)
  }
  return String(value)
}

const SERVICE_STYLES: Record<Telegram['service'], string> = {
  write: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  read: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  response: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
}

export function TelegramMonitor({
  lastTelegram,
  connected,
}: {
  lastTelegram: Telegram | null
  connected: boolean
}) {
  const [paused, setPaused] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [gaFilter, setGaFilter] = useState('')
  const [serviceFilter, setServiceFilter] = useState<ServiceFilter>('all')
  const telegrams = useTelegramHistory(lastTelegram, paused)
  const scrollRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const needle = gaFilter.trim()
    return telegrams.filter((telegram) => {
      if (serviceFilter !== 'all' && telegram.service !== serviceFilter) return false
      if (needle && !telegram.destination.includes(needle)) return false
      return true
    })
  }, [telegrams, gaFilter, serviceFilter])

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [filtered, autoScroll])

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-white p-4 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Telegram monitor
        </h2>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
            connected
              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200'
              : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-red-500'}`}
          />
          {connected ? 'live' : 'disconnected'}
        </span>

        <div className="ml-auto flex flex-wrap items-center gap-3 text-sm">
          <input
            type="text"
            value={gaFilter}
            onChange={(event) => setGaFilter(event.target.value)}
            placeholder="Filter by GA (e.g. 1/1)"
            className="rounded border border-neutral-300 bg-white px-2 py-1 text-sm text-neutral-900 placeholder:text-neutral-400 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
          />
          <select
            value={serviceFilter}
            onChange={(event) => setServiceFilter(event.target.value as ServiceFilter)}
            className="rounded border border-neutral-300 bg-white px-2 py-1 text-sm text-neutral-900 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
          >
            <option value="all">all services</option>
            <option value="write">write</option>
            <option value="read">read</option>
            <option value="response">response</option>
          </select>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(event) => setAutoScroll(event.target.checked)}
            />
            auto-scroll
          </label>
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            className={`rounded px-3 py-1 font-medium ${
              paused
                ? 'bg-amber-500 text-white hover:bg-amber-600'
                : 'bg-neutral-200 text-neutral-800 hover:bg-neutral-300 dark:bg-neutral-700 dark:text-neutral-100 dark:hover:bg-neutral-600'
            }`}
          >
            {paused ? 'Resume' : 'Pause'}
          </button>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="h-96 overflow-y-auto rounded border border-neutral-200 font-mono text-xs dark:border-neutral-800"
      >
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-neutral-100 text-left dark:bg-neutral-800">
            <tr>
              <th className="px-2 py-1">Time</th>
              <th className="px-2 py-1">Source</th>
              <th className="px-2 py-1">Destination</th>
              <th className="px-2 py-1">Service</th>
              <th className="px-2 py-1">DPT</th>
              <th className="px-2 py-1">Value</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((telegram, index) => (
              <tr
                key={`${telegram.timestamp}-${index}`}
                className="border-t border-neutral-100 dark:border-neutral-800"
              >
                <td className="px-2 py-1 whitespace-nowrap text-neutral-500 dark:text-neutral-400">
                  {formatTime(telegram.timestamp)}
                </td>
                <td className="px-2 py-1 whitespace-nowrap">{telegram.source}</td>
                <td className="px-2 py-1 whitespace-nowrap font-semibold">
                  {telegram.destination}
                </td>
                <td className="px-2 py-1 whitespace-nowrap">
                  <span
                    className={`rounded px-1.5 py-0.5 ${SERVICE_STYLES[telegram.service]}`}
                  >
                    {telegram.service}
                  </span>
                </td>
                <td className="px-2 py-1 whitespace-nowrap text-neutral-500 dark:text-neutral-400">
                  {telegram.dpt_id ?? '—'}
                </td>
                <td className="px-2 py-1 whitespace-nowrap">{formatValue(telegram.value)}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-2 py-6 text-center text-neutral-400">
                  No telegrams yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
