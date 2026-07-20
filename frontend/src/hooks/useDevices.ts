import { useEffect, useState } from 'react'
import { fetchDevices } from '../api'
import type { DeviceState, Telegram } from '../types'

/** Device state: initial snapshot via REST, then incrementally patched as
 * telegrams arrive. Any group_object (on *any* device) whose
 * group_address matches an incoming write/response telegram's
 * destination gets its value updated -- mirroring how a real bus
 * participant observes traffic on a shared GA regardless of who "owns"
 * it. This is a deliberate simplification: the real Bus only updates a
 * specific group_object when its own `write` flag is set (see
 * Bus._deliver in knx_sim/bus/router.py), so a device whose only object
 * on that GA lacks the write flag (e.g. a wall switch's "control", which
 * is transmit-only) wouldn't actually change server-side from an
 * external write the way this client-side approximation assumes. Judged
 * close enough for a live dashboard's display purposes -- perfectly
 * mirroring bus flag semantics client-side would need the backend to
 * push explicit per-object change events instead of raw telegrams. */
export function useDevices(lastTelegram: Telegram | null): DeviceState[] {
  const [devices, setDevices] = useState<DeviceState[]>([])

  useEffect(() => {
    let cancelled = false
    fetchDevices()
      .then((initial) => {
        if (!cancelled) setDevices(initial)
      })
      .catch((err: unknown) => {
        console.error('Failed to load devices', err)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (lastTelegram === null || lastTelegram.service === 'read') return
    const { destination, value } = lastTelegram
    setDevices((prev) =>
      prev.map((device) => {
        let changed = false
        const group_objects: Record<string, DeviceState['group_objects'][string]> = {}
        for (const [name, state] of Object.entries(device.group_objects)) {
          if (state.group_address === destination) {
            changed = true
            group_objects[name] = { ...state, value }
          } else {
            group_objects[name] = state
          }
        }
        return changed ? { ...device, group_objects } : device
      }),
    )
  }, [lastTelegram])

  return devices
}
