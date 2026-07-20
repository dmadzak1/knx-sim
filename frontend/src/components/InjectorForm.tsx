import { useState } from 'react'
import type { FormEvent } from 'react'
import { useGroupAddressNames } from '../hooks/useGroupAddressNames'
import { useInject } from '../hooks/useInject'
import type { Telegram } from '../types'

const COMMON_DPTS = ['1.001', '1.008', '1.010', '1.018', '3.007', '5.001', '5.004', '9.001', '9.004', '9.007']

export function InjectorForm() {
  const [destination, setDestination] = useState('')
  const [service, setService] = useState<Telegram['service']>('write')
  const [dptId, setDptId] = useState('1.001')
  const [rawValue, setRawValue] = useState('true')
  const [parseError, setParseError] = useState<string | null>(null)
  const { inject, pending, error } = useInject()
  const groupAddressNames = useGroupAddressNames()

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setParseError(null)

    if (service === 'read') {
      await inject({ destination, service: 'read' })
      return
    }

    let value: unknown
    try {
      value = JSON.parse(rawValue)
    } catch {
      setParseError(`"${rawValue}" isn't valid JSON (try true, 21.5, "text", or {"direction":true,"step_code":3})`)
      return
    }
    await inject({ destination, service, dpt_id: dptId, value })
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-white p-4 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Manual telegram injector
      </h2>
      <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-neutral-600 dark:text-neutral-300">Group address</span>
          <input
            type="text"
            list="known-group-addresses"
            required
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            placeholder="1/1/1"
            className="w-28 rounded border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-800"
          />
          <datalist id="known-group-addresses">
            {groupAddressNames.map((entry) => (
              <option key={entry.address} value={entry.address} label={entry.name} />
            ))}
          </datalist>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-neutral-600 dark:text-neutral-300">Service</span>
          <select
            value={service}
            onChange={(event) => setService(event.target.value as Telegram['service'])}
            className="rounded border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-800"
          >
            <option value="write">write</option>
            <option value="read">read</option>
            <option value="response">response</option>
          </select>
        </label>

        {service !== 'read' && (
          <>
            <label className="flex flex-col gap-1">
              <span className="text-neutral-600 dark:text-neutral-300">DPT</span>
              <input
                type="text"
                list="common-dpts"
                required
                value={dptId}
                onChange={(event) => setDptId(event.target.value)}
                className="w-24 rounded border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-800"
              />
              <datalist id="common-dpts">
                {COMMON_DPTS.map((dpt) => (
                  <option key={dpt} value={dpt} />
                ))}
              </datalist>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-neutral-600 dark:text-neutral-300">
                Value (JSON: true, 21.5, "text"...)
              </span>
              <input
                type="text"
                required
                value={rawValue}
                onChange={(event) => setRawValue(event.target.value)}
                className="w-48 rounded border border-neutral-300 bg-white px-2 py-1 font-mono dark:border-neutral-700 dark:bg-neutral-800"
              />
            </label>
          </>
        )}

        <button
          type="submit"
          disabled={pending}
          className="rounded bg-blue-600 px-4 py-1.5 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
      {(parseError ?? error) && (
        <p className="text-xs text-red-600 dark:text-red-400">{parseError ?? error}</p>
      )}
    </section>
  )
}
