import { DeviceGrid } from './components/DeviceGrid'
import { GroupAddressActivityView } from './components/GroupAddressActivityView'
import { InjectorForm } from './components/InjectorForm'
import { TelegramMonitor } from './components/TelegramMonitor'
import { useDevices } from './hooks/useDevices'
import { useGroupAddressActivity } from './hooks/useGroupAddressActivity'
import { useWebSocketTelegrams } from './hooks/useWebSocketTelegrams'

function App() {
  // The one shared WebSocket connection for the whole dashboard -- every
  // other piece of live state (device cards, GA activity, the telegram
  // table) derives incrementally from `lastTelegram` rather than each
  // opening its own socket. See useWebSocketTelegrams's docstring.
  const { lastTelegram, connected } = useWebSocketTelegrams()
  const devices = useDevices(lastTelegram)
  const activity = useGroupAddressActivity(lastTelegram)

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <header className="border-b border-neutral-200 px-6 py-4 dark:border-neutral-800">
        <h1 className="text-xl font-bold">knx-sim dashboard</h1>
      </header>
      <main className="flex flex-col gap-6 p-6">
        <DeviceGrid devices={devices} />
        <InjectorForm />
        <TelegramMonitor lastTelegram={lastTelegram} connected={connected} />
        <GroupAddressActivityView activity={activity} />
      </main>
    </div>
  )
}

export default App
