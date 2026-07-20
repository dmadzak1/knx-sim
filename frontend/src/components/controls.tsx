import { useEffect, useState } from 'react'

export function Toggle({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string
  value: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!value)}
      className={`flex w-full items-center justify-between gap-2 rounded px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
        value
          ? 'bg-blue-600 text-white hover:bg-blue-700'
          : 'bg-neutral-200 text-neutral-700 hover:bg-neutral-300 dark:bg-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-600'
      }`}
    >
      <span>{label}</span>
      <span>{value ? 'ON' : 'OFF'}</span>
    </button>
  )
}

export function Slider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = '',
  onCommit,
  disabled,
}: {
  label: string
  value: number
  min?: number
  max?: number
  step?: number
  unit?: string
  onCommit: (next: number) => void
  disabled?: boolean
}) {
  const [local, setLocal] = useState(value)

  useEffect(() => setLocal(value), [value])

  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="flex justify-between text-neutral-600 dark:text-neutral-300">
        <span>{label}</span>
        <span className="font-mono">
          {local.toFixed(1)}
          {unit}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={local}
        disabled={disabled}
        onChange={(event) => setLocal(Number(event.target.value))}
        onPointerUp={() => onCommit(local)}
        onKeyUp={() => onCommit(local)}
        className="w-full"
      />
    </label>
  )
}

export function NumberField({
  label,
  value,
  step = 0.5,
  unit = '',
  onCommit,
  disabled,
}: {
  label: string
  value: number
  step?: number
  unit?: string
  onCommit: (next: number) => void
  disabled?: boolean
}) {
  const [local, setLocal] = useState(String(value))

  useEffect(() => setLocal(String(value)), [value])

  function commit(): void {
    const parsed = Number(local)
    if (!Number.isNaN(parsed)) onCommit(parsed)
  }

  return (
    <label className="flex items-center justify-between gap-2 text-sm">
      <span className="text-neutral-600 dark:text-neutral-300">{label}</span>
      <span className="flex items-center gap-1">
        <input
          type="number"
          step={step}
          value={local}
          disabled={disabled}
          onChange={(event) => setLocal(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') commit()
          }}
          className="w-20 rounded border border-neutral-300 bg-white px-2 py-1 text-right dark:border-neutral-700 dark:bg-neutral-800"
        />
        <span className="text-neutral-500">{unit}</span>
      </span>
    </label>
  )
}

export function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-neutral-600 dark:text-neutral-300">{label}</span>
      <span className="font-mono text-neutral-900 dark:text-neutral-100">{value}</span>
    </div>
  )
}
