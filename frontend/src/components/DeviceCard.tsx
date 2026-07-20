import type { ReactNode } from 'react'
import { NumberField, ReadOnlyField, Slider, Toggle } from './controls'
import { useInject } from '../hooks/useInject'
import type { DeviceState } from '../types'

function asBool(value: unknown): boolean {
  return value === true
}

function asNumber(value: unknown): number {
  return typeof value === 'number' ? value : 0
}

/** Dispatches to a type-specific body matching each device's actual
 * group-object names (see each device's from_config() in knx_sim/devices/
 * for the authoritative list) -- a generic "render a control per writable
 * DPT" approach would be simpler but gets the semantics wrong for devices
 * like a wall switch (whose only object is transmit-only, not writable,
 * yet is very much meant to be triggered from the UI) or a presence
 * sensor (writable-looking DPT 1.018, but the real device has no write
 * flag at all -- KNX presence sensors only ever report, never accept
 * writes). Type-aware cards get this right without special-casing. */
export function DeviceCard({ device }: { device: DeviceState }) {
  const { inject, pending, error } = useInject()
  const go = device.group_objects

  let body: ReactNode
  switch (device.type) {
    case 'switch':
      body = (
        <Toggle
          label="Switch"
          value={asBool(go.status?.value)}
          disabled={pending}
          onChange={(next) =>
            void inject({ destination: go.control.group_address, dpt_id: '1.001', value: next })
          }
        />
      )
      break

    case 'wall_switch':
      body = (
        <Toggle
          label="Press"
          value={asBool(go.control?.value)}
          disabled={pending}
          onChange={(next) =>
            void inject({ destination: go.control.group_address, dpt_id: '1.001', value: next })
          }
        />
      )
      break

    case 'dimmer':
      body = (
        <>
          <Toggle
            label="Switch"
            value={asBool(go.switch_status?.value)}
            disabled={pending}
            onChange={(next) =>
              void inject({ destination: go.switch.group_address, dpt_id: '1.001', value: next })
            }
          />
          <Slider
            label="Brightness"
            unit="%"
            value={asNumber(go.brightness_status?.value)}
            disabled={pending}
            onCommit={(next) =>
              void inject({
                destination: go.brightness.group_address,
                dpt_id: '5.001',
                value: next,
              })
            }
          />
        </>
      )
      break

    case 'blind':
      body = (
        <>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                void inject({ destination: go.move.group_address, dpt_id: '1.008', value: false })
              }
              className="flex-1 rounded bg-neutral-200 px-2 py-1 text-sm font-medium hover:bg-neutral-300 disabled:opacity-50 dark:bg-neutral-700 dark:hover:bg-neutral-600"
            >
              ▲ Up
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                void inject({ destination: go.stop.group_address, dpt_id: '1.010', value: true })
              }
              className="flex-1 rounded bg-neutral-200 px-2 py-1 text-sm font-medium hover:bg-neutral-300 disabled:opacity-50 dark:bg-neutral-700 dark:hover:bg-neutral-600"
            >
              ■ Stop
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                void inject({ destination: go.move.group_address, dpt_id: '1.008', value: true })
              }
              className="flex-1 rounded bg-neutral-200 px-2 py-1 text-sm font-medium hover:bg-neutral-300 disabled:opacity-50 dark:bg-neutral-700 dark:hover:bg-neutral-600"
            >
              ▼ Down
            </button>
          </div>
          <Slider
            label="Position (0=open, 100=closed)"
            unit="%"
            value={asNumber(go.position_status?.value)}
            disabled={pending}
            onCommit={(next) =>
              void inject({
                destination: go.position.group_address,
                dpt_id: '5.001',
                value: next,
              })
            }
          />
          {asBool(go.moving_status?.value) && (
            <p className="text-xs text-amber-600 dark:text-amber-400">Moving…</p>
          )}
        </>
      )
      break

    case 'thermostat':
      body = (
        <>
          <ReadOnlyField
            label="Temperature"
            value={`${asNumber(go.temperature?.value).toFixed(1)} °C`}
          />
          <NumberField
            label="Setpoint"
            unit="°C"
            step={0.5}
            value={asNumber(go.setpoint?.value)}
            disabled={pending}
            onCommit={(next) =>
              void inject({ destination: go.setpoint.group_address, dpt_id: '9.001', value: next })
            }
          />
          <ReadOnlyField
            label="Heating"
            value={asBool(go.heating_demand?.value) ? 'demanded' : 'idle'}
          />
        </>
      )
      break

    case 'presence':
      body = (
        <ReadOnlyField
          label="Presence"
          value={asBool(go.presence?.value) ? 'occupied' : 'clear'}
        />
      )
      break

    default:
      // Unknown/future device type: fall back to a plain read-only dump
      // of every group object rather than rendering nothing.
      body = (
        <>
          {Object.entries(go).map(([name, state]) => (
            <ReadOnlyField key={name} label={name} value={String(state.value)} />
          ))}
        </>
      )
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-white p-3 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="truncate text-sm font-semibold text-neutral-900 dark:text-neutral-100">
          {device.name ?? device.individual_address}
        </h3>
        <span className="shrink-0 text-xs text-neutral-400">{device.type}</span>
      </div>
      {body}
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
