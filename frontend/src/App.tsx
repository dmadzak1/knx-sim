import { TelegramMonitor } from './components/TelegramMonitor'

function App() {
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <header className="border-b border-neutral-200 px-6 py-4 dark:border-neutral-800">
        <h1 className="text-xl font-bold">knx-sim dashboard</h1>
      </header>
      <main className="flex flex-col gap-4 p-6">
        <TelegramMonitor />
      </main>
    </div>
  )
}

export default App
