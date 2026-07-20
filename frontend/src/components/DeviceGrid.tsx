import { DeviceCard } from './DeviceCard'
import type { DeviceState } from '../types'

const UNGROUPED = 'Ungrouped'

function groupByRoom(devices: DeviceState[]): Map<string, DeviceState[]> {
  const rooms = new Map<string, DeviceState[]>()
  for (const device of devices) {
    const room = device.room ?? UNGROUPED
    const existing = rooms.get(room)
    if (existing) {
      existing.push(device)
    } else {
      rooms.set(room, [device])
    }
  }
  // Ungrouped last, everything else alphabetical -- a stable, predictable order.
  return new Map(
    [...rooms.entries()].sort(([a], [b]) => {
      if (a === UNGROUPED) return 1
      if (b === UNGROUPED) return -1
      return a.localeCompare(b)
    }),
  )
}

export function DeviceGrid({ devices }: { devices: DeviceState[] }) {
  if (devices.length === 0) {
    return <p className="text-sm text-neutral-400">No devices.</p>
  }

  const rooms = groupByRoom(devices)

  return (
    <div className="flex flex-col gap-6">
      {[...rooms.entries()].map(([room, roomDevices]) => (
        <section key={room} className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold tracking-wide text-neutral-500 uppercase dark:text-neutral-400">
            {room}
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {roomDevices.map((device) => (
              <DeviceCard key={device.individual_address} device={device} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
