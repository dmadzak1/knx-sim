import type { GroupAddressActivity } from '../hooks/useGroupAddressActivity'

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleTimeString(undefined, { hour12: false })
}

export function GroupAddressActivityView({
  activity,
}: {
  activity: GroupAddressActivity[]
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-white p-4 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Group address activity
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead className="text-left text-neutral-500 dark:text-neutral-400">
            <tr>
              <th className="px-2 py-1">Name</th>
              <th className="px-2 py-1">Group address</th>
              <th className="px-2 py-1">Last value</th>
              <th className="px-2 py-1">Last seen</th>
              <th className="px-2 py-1">Messages</th>
              <th className="px-2 py-1">Rate (msg/min)</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {activity.map((entry) => (
              <tr
                key={entry.groupAddress}
                className="border-t border-neutral-100 dark:border-neutral-800"
              >
                <td className="px-2 py-1 font-semibold">{entry.name ?? '—'}</td>
                <td className="px-2 py-1">{entry.groupAddress}</td>
                <td className="px-2 py-1">{formatValue(entry.lastValue)}</td>
                <td className="px-2 py-1 text-neutral-500 dark:text-neutral-400">
                  {formatTime(entry.lastSeen)}
                </td>
                <td className="px-2 py-1">{entry.count}</td>
                <td className="px-2 py-1">{entry.ratePerMinute}</td>
              </tr>
            ))}
            {activity.length === 0 && (
              <tr>
                <td colSpan={6} className="px-2 py-6 text-center text-neutral-400">
                  No activity yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
