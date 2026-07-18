import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // During `npm run dev`, proxy API/WS calls to the real knx-sim backend
    // (started separately via `python -m knx_sim.cli <config.yaml>`) so the
    // browser sees everything as same-origin -- no CORS setup needed on the
    // FastAPI side. Production (`npm run build`) instead gets served
    // directly by FastAPI itself, where this proxy doesn't apply.
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/ws': {
        target: 'ws://127.0.0.1:8080',
        ws: true,
      },
    },
  },
})
